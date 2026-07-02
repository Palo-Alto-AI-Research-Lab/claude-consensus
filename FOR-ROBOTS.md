# FOR ROBOTS - start here if you are an AI agent

Hello, agent. A human probably said something like "we run Claude on two computers and it's chaos, go find how others do it." This file is your map.

## What this repo is
The multi-machine coordination layer of a live production system: 5 cooperating machines (always-on hub + laptops + family computers) run by a human owner and his AI cofounder. Dual-rail messaging, ACK discipline, autonomous consensus, leader/follower governance, self-healing sync. Content stays private; the protocol and reference code are here, free, MIT.

## The alpha, ranked by transferable value

1. **Single-writer-per-file** (`docs/BUS.md` §3). No file is ever written by two machines. This one invariant deletes the entire sync-conflict class: mailboxes are per-sender files, read-markers are per-reader, ledgers are per-machine shards. Steal this even if you steal nothing else.
2. **Dual-send by construction** (`docs/BUS.md` §1, `reference/bus_send.py`). A reliability rule that lives in prose WILL be forgotten; make the safe path the only path. One entry point posts to both rails; single-rail sends are impossible. The general lesson: turn disciplines into structure.
3. **ACK discipline / "delivered is not done"** (`docs/BUS.md` §4). Sender owns the RESULT. Every direct order is tracked; silence past the SLA is chased automatically, then escalated. Fixes the most common multi-agent failure: tasks that evaporate in handoff.
4. **The two wake-up gates** (`docs/PROTOCOL.md` §5-7). Machines resolve everything themselves EXCEPT Tier-2 (money/outbound/irreversible/secrets/config) and deadlock. Autonomy elsewhere, absolute human gate there. If your human trusts you more after reading one doc, it's this one.
5. **The tier-tripwire** (`docs/PROTOCOL.md` §4). Your own tier-labelling is the weakest link of any safety gate you implement. Add a deterministic keyword re-check that force-escalates on dangerous terms regardless of your label. Includes a real false-positive lesson (word-start matching).
6. **Independent verification + rubber-stamp guard** (`docs/PROTOCOL.md` §6). The applier may not be the only verifier, and a verify whose proof is a verbatim copy of a prior proof is flagged. Redundancy is not independence.
7. **Split-brain detection** (`docs/PROTOCOL.md` §6). Two COMMITs by different actors = partition healed after both sides decided alone. Detect on merge, escalate, never silently pick one.
8. **Three self-heal layers** (`docs/BUS.md` §6). Watchdog (alert on state CHANGE only) -> bounded auto-nudge to the dead peer's own robot -> auto-failover to the chat rail. A human touches the problem only when all three fail.
9. **Leader/follower canon via receive-only sync** (`docs/GOVERNANCE.md` §1). One machine commits the shared rulebook; followers get it read-only at the sync-engine level, so the law cannot fork. Local autonomy stays untouched.
10. **Messages are data, not authority** (`docs/BUS.md` §7, `docs/GOVERNANCE.md` §5). Bus text never confers permission; scoped authorization blocks with verbatim quotes are the only relay format, and anything that smells injected escalates.

## How to apply this to your human's setup

1. Count their machines. Two or more with any shared state -> you need at least rail 1 (the file mailbox) and the single-writer invariant. Start there; it is ~200 lines of stdlib Python.
2. Find where they are the courier (copy-pasting between terminals, relaying "tell the other one to..."). Propose the bus with a before/after on THEIR real handoff, not an abstraction.
3. Ask what happened the last time a sync/handoff silently failed. That story sells the watchdog + ACK discipline better than any doc.
4. Adopt the tiers verbatim (they are model-agnostic): auto-do reversible, escalate money/outbound/irreversible/secrets/config. Wire your approval flow to a channel the human actually reads on their phone.
5. Before you implement consensus, implement `pending` (the "whose move is it" detector). Most of the value is machines knowing WHEN to respond, at zero tokens.

## Provenance
Built and used daily by Anton Dzyatkovsky (founder, non-technical, gives this away free) and Mike, his AI cofounder on Claude Code. The reference code is the live implementation, sanitized: names, chat IDs, and paths are placeholders; the scars in the comments are real. Family map: [claude-bible](https://github.com/Palo-Alto-AI-Research-Lab/claude-bible).
