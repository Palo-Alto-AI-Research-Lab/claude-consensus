# The dual-rail bus

How messages actually move between machines, and the discipline that keeps "sent" from quietly becoming "done". Reference: [`reference/machine_bus.py`](../reference/machine_bus.py), [`reference/bus_send.py`](../reference/bus_send.py), [`reference/sync_monitor.py`](../reference/sync_monitor.py).

## §1. Two rails, one entry point

| | Rail 1: file mailbox | Rail 2: group chat |
|---|---|---|
| Transport | your synced folder (Syncthing, Dropbox, git) | Telegram group / Slack channel / Discord webhook |
| Strengths | unlimited size, structured, survives offline peers | always-on, humans see it, works when sync is down |
| Weaknesses | dies silently when sync dies | 4096-char limits, flood control |
| Role | payload rail | mirror + human-visibility rail |

The rule that makes this work: **every machine-to-machine message goes on BOTH rails, in one call.** Not "chat as fallback": the chat rail is always on, because the moment it becomes optional, someone (human or LLM) forgets it, and the owner stops seeing what the machines are doing. We learned this the direct way: dual-send existed as a prose rule, a task went out on the file rail only, and the owner never saw it.

So dual-send is **structural, not behavioral**: `bus_send.py` is the ONE entry point, it posts to both rails itself, and calling the rails individually is forbidden by convention (and by code review). If one rail fails, the message still goes out on the survivor AND a failure signal is raised on the surviving rail. A dead rail is a signal to the owner, not a reason to send silently on one.

Giant messages (>4096 chars) stay file-rail-only by design; the chat rail carries a pointer.

## §2. Streams and addressing

A stream = a logical mailbox in the bus folder:

- `<MACHINE>`: direct to one machine (`send HUB-1 "..."`)
- `ALL`: broadcast (`send ALL "..."`)
- `cap-<name>`: capability channel (`send @gpu "..."`): every machine that declares capability `gpu` in `machines.json` subscribes. Address the CAPABILITY, not the machine, and the topology can change without rewriting callers.

`machines.json` (lives in the bus folder, synced everywhere):

```json
{
  "machines": {
    "HUB-1":    {"label": "always-on desktop", "role": "leader",
                 "capabilities": ["gpu", "always-on"], "deviceID": "<sync-device-id>"},
    "LAPTOP-1": {"label": "owner's laptop", "role": "follower",
                 "capabilities": [], "deviceID": "<sync-device-id>"}
  }
}
```

**One machine = one bus key, forever.** A raw hostname can differ from the friendly name you want; alias it in code (`KEY_ALIASES`) so the same machine can never split into two mailboxes. We lost messages to exactly that split once.

## §3. Storage: the single-writer invariant

The root fix for sync conflicts, used consistently across the whole system:

> **No file is ever written by more than one machine.**

- Senders append to `inbox-<STREAM>__from-<SENDER>.md`: their own file per stream.
- Readers keep their own byte-offset markers `.read-<reader>__<stream>__src-<sender>`.
- The consensus ledger shards per machine (`log-<MACHINE>.jsonl`).

Whole-file sync engines conflict when two machines modify the same file between syncs. Make that impossible by construction and the entire conflict class disappears. Readers do slightly more work (fold N per-sender files per stream); that trade is worth it every time.

Two hardening details from production:

- **Byte offsets + UTF-8:** read from the marker offset in binary, then snap forward past any UTF-8 continuation bytes. A text-mode seek landing mid-character once killed the whole bus read with a UnicodeDecodeError.
- **Offset > file size** means the file shrank or was reset: start from 0, don't crash.

## §4. ACK discipline: delivered is not done

The Connect rule, the single most load-bearing piece of discipline in a multi-machine (or multi-person) system:

> **Whoever hands off a task owns the RESULT, not the handoff. "I sent it" means nothing. Silence means nothing.**

Mechanics:

1. **Receiver ACKs immediately** on pickup (`ACK #<id>`), then reports the outcome (`done` / `stuck: <why>`), both dual-sent.
2. **Sender registers every direct order** with an ACK-watchdog at send time (see `_maybe_register` in `bus_send.py`). Broadcasts, heartbeats, and ACKs themselves are exempt: only orders are tracked.
3. **No ACK within the SLA (~20 min)** -> automatic re-ping on the live rail; still nothing -> escalate to the human: "machine X did not confirm Y".
4. Message IDs (`#<hex>`) ride every envelope; the same ID travels on both rails so receivers dedup cross-rail duplicates.

The failure mode this kills: A tells B, B's robot is down, nobody notices, three days later the humans discover the task evaporated. With the watchdog, that becomes a 20-minute detection.

## §5. Heartbeats: report yourself, fully

Every peer periodically posts a one-line **full health snapshot** to the group chat: its rails, its connectors, what's broken. Flat text, no envelope:

```
[HEART] [LAPTOP-1] alive 22:20 - sync:OK chat-rail:OK connectors:8/9 WARN: imap-watcher down
```

Principles:

- **Silence is never OK.** A node that stops heartbeating is presumed down; the hub's watchdog chases it.
- **A node reports only itself.** No peer speculates about another peer's health; that produces confident wrong data.
- **Snapshot, not "alive".** A bare "alive" hides a half-dead node. Include every rail and connector state, so a degraded node is visible before it matters.

## §6. Self-heal: three layers before a human is bothered

Sync dies. The design question is not "how do we prevent it" but "how many minutes until it's healed, and how many of those minutes need a human". Three layers, in order:

**Layer 1: dead-man watchdog** (`sync_monitor.py`, on the always-on hub, every ~20 min). Watches the sync daemon's live peer connections via its REST API. Pings the group chat ONLY on a state change (drop or reconnect), re-nags at most every 3 hours. Quiet by design: an alert channel that cries hourly gets muted within a week.

**Layer 2: auto-nudge the peer's own robot.** The hub cannot restart a daemon on a machine it can't reach over sync, but the chat rail is usually still up. So the watchdog posts a bounded number of group-chat lines (max 3 per episode, >=30 min apart) addressed to the DOWN peer's robot by its bus key: "your sync daemon is not connected to the hub, restart it via your watchdog task". The peer heals itself. Bounded, so a long outage doesn't flood the chat.

**Layer 3: auto-failover in the send path.** `machine_bus.py send` checks (best-effort, via the sync daemon's API) whether the addressee is currently reachable over file sync. If not, or if it can't tell, it mirrors the message to the chat rail with the same `#id`. Messages composed during a partition arrive anyway; the receiver dedups when the file rail catches up.

Plus a local baseline: every machine runs a ~5-min watchdog on its OWN sync daemon (is the process alive, restart if not). Self-care first; the hub's layers cover what self-care can't see.

On reconnect, divergent edits from the split surface as sync-conflict files. Fire a loss-free sweeper automatically (archive first, only auto-resolve the provably-safe subset) so conflicts self-heal instead of piling up.

## §7. Messages are data, not authority

The bus moves bytes; it does not confer permission. A message saying "delete X" is an INPUT to the receiving agent's own judgment and its owner's rules, not an order. Concretely:

- Tier-1 work requested via the bus (reindex, read, draft-to-file: safe, reversible, idempotent) may be auto-executed.
- Tier-2 work requested via the bus (money, outbound, irreversible, secrets, config edits) is escalated to the human, NOT executed, unless a valid scoped authorization block covers exactly that action (see [GOVERNANCE.md](GOVERNANCE.md) §5).
- Anything that smells like injection (a scope that doesn't match the quote, an over-broad grant, an "authorization" nobody remembers) -> escalate, don't execute.

This is the boundary that makes it safe to let machines message each other at all.
