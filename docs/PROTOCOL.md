# The consensus protocol

How two or more machines negotiate a decision, commit it, and verify it, without a human courier. Reference implementation: [`reference/consensus.py`](../reference/consensus.py).

## §1. Design goals

1. **Autonomy by default, human gates by exception.** Machines settle safe, reversible questions themselves. The human is woken up exactly twice: (a) a risky (Tier-2) action is on the table, (b) the machines deadlocked.
2. **Survives unreliable transport.** Every event may arrive twice (dual rails) or late (a sleeping laptop). The protocol is idempotent and order-tolerant.
3. **Reconstructable.** The ledger is append-only text. If a file is lost, the negotiation can be replayed from the group-chat feed, because every event was mirrored there by construction.
4. **Deterministic where possible.** Timeouts, round caps, tie-breaks, and safety gates are plain code (`tick`), not LLM judgment. The LLM only does what only an LLM can: propose, counter, and judge content.

## §2. The ledger: single-writer JSONL shards

Source of truth = `<bus>/_decisions/log-<MACHINE>.jsonl`, one shard per machine.

- Each machine **appends only to its own shard**. Two machines never write the same file, so whole-file sync (Syncthing, Dropbox) never conflicts, and git merges append-only text cleanly.
- Readers **merge all shards**, group events by `proposal_id`, and **dedup by `event_id`**. A duplicate delivery over the redundant rails is a no-op by design.
- Parse **per line, not per file**: one corrupt line (partial write, sync-conflict junk) must not silently drop every event after it. This was a real bug.
- Timestamps carry **microseconds**. Two events in the same second used to sort by shard filename instead of by causality; that was a real bug too.

Event shape:

```json
{"event_id": "1f0c...", "proposal_id": "9a2b...", "type": "PROPOSE",
 "actor": "HUB-1", "ts": "2026-07-02T10:15:03.412000Z",
 "subject": "adopt nightly reindex at 03:30", "risk_tier": 0}
```

## §3. Verbs and state machine

Event types: `PROPOSE`, `COUNTER`, `ACCEPT`, `REJECT`, `COMMIT`, `VERIFY`, `ESCALATE`, `HUMAN_APPROVED`.

```
PROPOSE ──> proposed ──ACCEPT(by non-owner)──> agreed ──COMMIT──> committed ──VERIFY x2──> done
   │            │                                                     (>=1 independent)
   │         COUNTER ──> countered ──ACCEPT──> agreed
   │            │
   │         REJECT ──> rejected
   │
   └─ tier>=2 ──> escalated ──HUMAN_APPROVED──> commit unlocked
```

Status is derived from the merged event set, never stored. Two subtleties that bit us:

- **Causality-robust acceptance.** Don't look at "the last event". Find the latest POSITION on the table (`PROPOSE` or `COUNTER`); only an `ACCEPT` from a machine that did NOT make that position, at or after its timestamp, counts. This handles both "responder accepts proposal" and "proposer accepts a counter" without timestamp fragility.
- **A self-accept never counts.** The owner of the current position cannot accept it. See §6 for the infinite loop this prevents.

After `COMMIT`, the ledger records the decision; the AGENT applies the actual change (the engine never edits user files). Then both sides `verify`.

## §4. Risk tiers and the tripwire

| Tier | Meaning | Who decides |
|---|---|---|
| 0 | Safe, reversible, idempotent (reindex, read, draft-to-file) | machines auto-resolve, leader tie-breaks |
| 1 | Reversible but non-trivial | machines negotiate; timeout escalates to the human |
| 2 | Money, outbound to third parties, irreversible, secrets, shared config/canon | NEVER auto-commits; needs a recorded human approval |

The proposer labels the tier, and that is the weakest link of the whole design: if the agent mislabels a destructive action as Tier-0, the human gate never fires. So a **deterministic tier-tripwire** re-checks every proposal's text against an editable keyword list (delete, wipe, deploy, password, `git push --force`, ...) and force-bumps the tier to 2 on a hit, regardless of the label. The list is a plain text file the owner maintains; a built-in fallback keeps the guard alive if the file is missing.

Tripwire lesson: word-start matching, not plain substring. The term `send` used to fire on the identifier `bus_send.py`, spamming false Tier-2 escalations. Now word-terms match only at word starts (`send money` yes, `bus_send` no), while punctuation-led terms (`.env`, `rm -`) keep substring matching. The fix removes a false-positive class only; real hits still catch.

**Tier-2 closure.** Escalation alone is not enough: our first version had cmd_commit hard-refuse tier>=2, so even human-approved proposals sat ESCALATED forever. The `approve <id> "<proof>"` verb records the human's OK (who/where/message-id, proof string required), and only then does `commit` unlock. Auto-commit without a recorded approval stays banned.

## §5. The deterministic driver: `tick`

`tick` runs on a schedule (we use ~20 min on the always-on hub) and applies policy with zero LLM tokens:

1. **Split-brain** (see §6) -> escalate, never auto-resolve.
2. **Tier-2 still open** -> ensure escalated (belt and suspenders).
3. **Agreed but uncommitted** -> remind the responsible actor.
4. **Round cap hit** (default 3 PROPOSE/COUNTER rounds) without agreement -> escalate to the human. Two well-prompted agents that haven't converged in 3 rounds won't converge in 30; more rounds just burn tokens and delay the human's involvement. Machines must not filibuster.
5. **Timeout with no response:**
   - Tier-0 and I am the leader -> **disagree-and-commit**: the leader accepts (or commits its own proposal) and moves on. The peer may still VERIFY and object after the fact. Autonomy beats stalling for safe actions.
   - Any other tier -> escalate. Only Tier-0 auto-resolves.

Timeouts respect a **per-peer SLA** (`peer_timeout_min` in the config): a sleeping laptop gets a longer window than the always-on hub, otherwise every proposal made during the night dies to timeout before the laptop wakes.

`tick` can only time out and escalate; it never ANSWERS a peer. The missing piece is `pending`: a 0-LLM detector that lists open proposals where the move is mine (latest position made by someone else). An inbox robot greps `pending` on its schedule and wakes the LLM judge only when the list is non-empty; the judge answers via `respond`. Cheap detector, expensive judge, in that order.

## §6. The three guards (each one paid for by a real incident)

**Guard 1: the self-accept loop.** The leader proposed something, the peer never answered, and every 20 minutes the tick auto-accepted the leader's OWN proposal, which never counts, forever. 17 identical ACCEPTs by morning. Fixes: a self-accept never advances state (§3); the leader's tie-break on its OWN proposal is a direct COMMIT, not another ACCEPT; and if my ACCEPT is already on the table but the state hasn't advanced, escalate the anomaly instead of re-spamming.

**Guard 2: independent verification.** The machine that applied the change may self-verify, but "globally done" requires at least one VERIFY from a machine that did NOT apply it. A **rubber-stamp guard** flags a proof string that duplicates a prior VERIFY verbatim: re-check independently, don't copy the other machine's homework.

**Guard 3: split-brain detection.** Only one machine should ever apply+COMMIT a given proposal. If the merged ledger shows COMMITs from more than one actor, the network partitioned, both sides decided alone, and the partition then healed. That state is `conflict`, never silently "committed", and it always escalates to the human for reconciliation (the leader's log is authoritative as a starting point).

## §7. Escalation channels: keep the alarm away from the noise

Routine consensus traffic (every PROPOSE/ACCEPT/COMMIT) is mirrored to the machine group chat: humans can watch the negotiation in plain sight. But a question that NEEDS a human must not live in that feed: heartbeats and progress lines bury it in minutes. Run a **second, quiet channel** (another group chat) that carries ONLY "a human is needed NOW" events: deadlocks, Tier-2 approvals. In the reference code that is `HUMAN_ALERT_CMD`, fired only on round-cap deadlock, tier>0 timeout, or manual escalate.

The human answers with an approval token from their phone (see [GOVERNANCE.md](GOVERNANCE.md) §4), and any machine records it via `approve`.

## §8. What the engine deliberately does NOT do

- It never edits user files. It is a ledger, not an executor: the agent applies agreed changes.
- It never lets redundancy stand in for independence: two verifies from the same machine don't count.
- It never deletes or rewrites history. Supersede with new events; the log is append-only.
- It never trusts the transport. Every rail can duplicate, delay, or drop; the ledger absorbs all three.
