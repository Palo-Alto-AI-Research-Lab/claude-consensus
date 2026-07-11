# Failure modes

Every guard in this engine exists because something broke first. This page is the
scar tissue: each known failure, the root cause, the guard that now catches it,
and a link to the exact code. Three of them (C, D, E) are reproduced live by
[`demo/demo.py`](../demo/demo.py); run it and watch them fire.

Two honesty notes up front:

- **These are the failures we know about.** A guard is evidence of a past bug, not
  a proof of future safety. New failure modes will appear; when they do they get a
  scar here, not a silent patch.
- **The published [`reference/consensus.py`](../reference/consensus.py) is a
  sanitized subset of our production engine.** Most guards ship in the reference
  (line links below). A few defend against fleet-specific incidents and live only
  in production; those are marked **[production-only]** and explained rather than
  hidden, because "we run more than we published" is exactly the kind of thing an
  eval should surface.

---

## A. The leader's infinite self-accept loop

**Symptom.** Overnight, the leader wrote 17 identical `ACCEPT` events on its own
proposal, one every ~20 minutes, and never converged.

**Root cause.** A `tick` on a timed-out Tier-0 proposal did a "leader
disagree-and-commit" by casting an `ACCEPT`. But an `ACCEPT` only counts toward
agreement when it comes from a machine that did **not** make the latest position
(you cannot accept your own proposal into agreement). So the leader's self-accept
never advanced the state, and the next tick did it again, forever.

**Guard.** On a Tier-0 timeout of the leader's **own** proposal, the tie-break is
now a direct `COMMIT` (decision of record), not a self-`ACCEPT`. A self-accept
that cannot advance state is never re-cast.
[`reference/consensus.py` cmd_tick, the `owner == ME` branch](../reference/consensus.py#L534-L543)

**Lesson.** A retry that re-issues an action which provably cannot change state is
an infinite loop with extra steps. Make the terminal action terminal.

---

## B. Tier mis-classification (the tripwire, and its false positive)

**Symptom (the danger).** The whole Tier-2 -> human-gate safety depends on the
agent labelling `--tier` correctly. Mislabel a destructive action as Tier-0 and
the gate never fires.

**Guard.** A deterministic keyword tripwire bumps any proposal to Tier-2 when its
subject contains a dangerous verb (`delete`, `send`, `transfer`, `publish`,
`revoke`, `.env`, ...), regardless of the label the agent chose. Safety no longer
depends on the model getting the tier right.
[`reference/consensus.py` _tripwire_hit](../reference/consensus.py#L89-L106)
· demo scenario **C** fires this on `"delete the archived leads table"`.

**Symptom (the scar).** The first tripwire matched substrings, so the identifier
`bus_send.py` tripped the term `send` and force-escalated harmless proposals that
merely *mentioned* a filename.

**Root cause.** Substring matching does not respect word boundaries.

**Fix.** Word-terms match only at a word start (not preceded by another word char),
so `send` fires on `"send money"` and `"sending"` but not on `bus_send`. Suffix
inflections still match; phrase terms like `.env` and `rm -` keep plain substring
matching. The gate stays fail-safe: this removed a false class only, real terms
still catch. Same code link as above.

**Lesson.** A safety gate that cries wolf gets disabled by the humans it annoys.
Precision is a safety property, not a nicety.

---

## C. A corrupt shard line eating everything after it

**Symptom.** One malformed line in a shard (a partial write, sync-conflict junk)
silently dropped **every event after it** in that file. State went stale with no
error.

**Root cause.** The reader parsed the whole file as one unit: a single bad line
aborted the parse of the rest.

**Guard.** The reader parses **per line, not per file**. A line that fails to parse
is skipped; the events around it are still read.
[`reference/consensus.py` _all_events](../reference/consensus.py#L155-L179)
· demo scenario **E** injects `{"event_id": "partial-write-junk", "type": "COMM`
into a shard and proves the `COMMIT` written after it is still read.

**Lesson.** In an append-only log fed by unreliable writers, corruption is local.
Make the reader treat it that way.

---

## D. Split-brain: two machines commit the same proposal

**Symptom.** During a network partition each side saw only `agreed`, believed it
owned the apply, and committed. When the partition healed, two conflicting
`COMMIT` events existed for one proposal.

**Guard (detection, not prevention).** Two `COMMIT` events from distinct actors on
one proposal is detected on merge and marked `conflict` - never silently
"committed". `tick` escalates it to the human for reconciliation; the leader's log
is authoritative.
[`_state` split-brain check](../reference/consensus.py#L216-L220)
· [`cmd_tick` conflict escalation](../reference/consensus.py#L498-L507)
· demo scenario **D** partitions the ledger, commits on both islands, heals, and
shows `tick` catch it.

**Honest limitation.** This **detects** split-brain, it does not **prevent** it. A
partition can still produce a double apply; the guarantee is that it never passes
silently as success. Prevention would need a real distributed lock, which we
deliberately did not build (see AK-47 simplicity: a non-technical owner must be
able to reason about this). The single-writer shard design makes the *ledger*
conflict-free; the *decision* still needs one owner per apply, and that is a
discipline the leader/follower rule ([GOVERNANCE.md](GOVERNANCE.md)) enforces.

**Lesson.** If you cannot cheaply prevent a fault, at minimum refuse to let it
masquerade as success.

---

## E. "Done" that nobody independently checked

**Symptom.** The machine that applied a change also verified it, and the system
called the task globally done on that single self-report. "Sent" becoming "done"
in a new costume.

**Guard.** "Globally done" requires **>=2 distinct verifiers, at least one of which
is not the committer.** The applier may self-verify, but an independent machine
must re-check. A rubber-stamp guard also rejects a proof that duplicates a prior
verify verbatim (copy-paste is not a re-check).
[`reference/consensus.py` cmd_verify](../reference/consensus.py#L397-L426)

**Lesson.** Verification by the party that did the work is a status update, not a
check. Independence is the whole value.

---

## F. Tier-2 proposals stuck escalated forever

**Symptom.** A Tier-2 action correctly escalated to the human, the human said yes
in chat, and then... nothing. `commit` hard-refused Tier-2, so the approval had no
way into the ledger and the proposal sat `escalated` permanently.

**Guard.** An `approve <id> "<proof>"` verb records the human OK as a first-class
event (with a required who/where/msg-id proof string). `commit` then allows Tier-2
**only** with a recorded approval; auto-commit without it stays banned.
[`cmd_approve`](../reference/consensus.py#L360-L378)
· [`cmd_commit` Tier-2 gate](../reference/consensus.py#L381-L394)
· demo scenario **B** shows the refusal, the approval, then the successful commit.

**Lesson.** A human gate needs an *exit*, not just an entrance. A safety stop with
no resume path is just a different outage.

---

## G. Same-second events sorting by filename instead of causality

**Symptom.** Two events written in the same second (a fast `PROPOSE` then
`COUNTER`) sometimes sorted by shard filename rather than by what actually
happened first, producing a wrong state.

**Guard.** Timestamps carry **microseconds**, which breaks same-second ties by real
order.
[`reference/consensus.py` _iso](../reference/consensus.py#L134-L137)

**Lesson.** If your ordering key has coarser resolution than your event rate, you
are sorting by luck.

---

## H. The deadlock question drowning in the heartbeat feed

**Symptom.** When machines genuinely deadlocked, the "a human is needed now" ping
went to the same busy machine-chat as every routine heartbeat, and the humans
missed it.

**Guard.** The deadlock/human-needed alert goes to a **separate, dedicated
channel** (configured via `HUMAN_ALERT_CMD`), kept strictly for the two cases a
human must answer: a Tier-2 action and a true deadlock. Routine traffic never
touches it.
[`reference/consensus.py` _human_alert](../reference/consensus.py#L261-L277)

**Lesson.** An alert channel that also carries noise is not an alert channel.

---

## I. Regressive votes from a restored backup **[production-only]**

**Symptom.** A machine restored from an older backup (or briefly running as a
duplicate instance) re-cast votes it had already superseded, re-opening settled
proposals with stale positions.

**Guard.** Our production engine keeps a per-machine **vote watermark**: a new vote
on proposal *P* must be strictly newer than that machine's last recorded vote on
*P*, else it is refused as regressive/replayed. The watermark lives in the synced
decisions directory, so restoring one machine from an old backup cannot roll it
back - peers re-sync the newer watermark.

**Why it is not in the reference.** This is slashing-protection against a
fleet-operations incident (backup restores, accidental double instances) rather
than a property of the protocol itself. The published
[`_append`](../reference/consensus.py#L149-L152) ships the simple single-writer
append so the reference stays minimal and easy to audit. If you run more than a
couple of machines with automated backups, add the watermark; the incident it
prevents is real.

**Lesson.** The protocol and the fleet operations around it fail in different ways.
Publishing the protocol honestly means saying which guards belong to which.

---

## Scars we keep in the comments

Beyond the above, the reference keeps smaller lessons inline: a `--details` string
that once got broadcast to the group chat as a message (only explicit verbs emit
now), and the general rule that a dead rail is a *signal*, not a silent downgrade
(see [BUS.md](BUS.md)). The comments in
[`reference/consensus.py`](../reference/consensus.py) are load-bearing; read them
as the changelog of everything that has bitten us.
