# Changelog

All notable changes to this project. Release cadence: twice a week (Mon & Thu), small commits land daily as work happens. Format: what shipped, in plain words.

## v0.2.0 - 2026-07-28

A month of running the engine across six machines produced four more guards. Every one is the
same shape as the first three: something the protocol trusted without checking. Both new files
self-test (`python <file>.py selftest`), and `fleet_sign.py` does a real signature round trip
including a tampering check — a signature selftest that never fails a verification proves nothing.

- `reference/protocol_guards.py` - **arbiter election**: the tie-break role no longer dies with the
  machine holding it. Elected from an ordered list by presence freshness, computed identically by
  every peer (so they agree without messaging), promoting only on positive evidence of life — a
  stale stamp fails over, an absent one does not. Gated behind an `armed` flag so an un-upgraded
  peer behaves identically. Announced once per episode, not once per tick.
- `reference/protocol_guards.py` - **proof grading**: `VERIFY` proof is graded `proven` only when it
  carries the residue of an action (exit code 0, a hash, a moved counter, a before/after pair).
  Armed from a timestamp; earlier history is grandfathered.
- `reference/protocol_guards.py` - **risk tracking**: a track (financial/secrets/outbound/canon/
  infra/general) classified independently of the tier the proposer chose, because the tripwire
  catches dangerous words but not a dangerous category carried at a low tier. Ships in shadow with
  a deliberately falsifiable verdict and a report that says whether the guard earned its keep.
- `reference/fleet_sign.py` - **machine identity**: Ed25519 detached signatures via `ssh-keygen -Y`,
  one public key file per machine (single writer, no conflicts), revocation list, allowed-signers
  assembled in memory at each verify. Unsigned (rollout gap) is kept strictly distinct from bad
  (tampering); bad is refused even during the dark phase. Two Windows scars documented in place:
  two ssh-keygen builds on PATH where one hangs on `-Y sign`, and the `newline=""` that stops
  CRLF armor from being corrupted into a false "tampered" verdict.
- `docs/PROTOCOL.md` §6a and `FOR-ROBOTS.md` - the four guards written up, plus a new
  "what is here versus what we run" section: the reference is sanitized and trimmed for reading,
  not a mirror, and now says which parts are deliberately absent.

## v0.1.0 - 2026-07-02

First public release. The multi-machine coordination layer, extracted from our live system:

- `docs/PROTOCOL.md` - the consensus protocol: propose -> counter -> accept -> commit over an append-only single-writer JSONL ledger; risk tiers + deterministic tier-tripwire; the deterministic `tick` driver (timeouts, round cap, leader disagree-and-commit); the three guards (self-accept loop, independent verify + rubber-stamp guard, split-brain detection); quiet human-alert channel separated from the noisy machine feed.
- `docs/BUS.md` - the dual-rail bus: file mailbox + group chat, dual-send by construction; streams and capability addressing; the single-writer invariant; ACK discipline ("delivered is not done"); full-snapshot heartbeats; three self-heal layers for sync.
- `docs/GOVERNANCE.md` - leader/follower canon over receive-only sync; risk tiers enforced in three independent places; machine identity tagging; remote approval token; scoped authorization relay; autonomy triggers.
- `reference/` - the sanitized live implementation, stdlib-only Python: `consensus.py`, `machine_bus.py`, `bus_send.py`, `sync_monitor.py`. Battle scars kept in the comments.
- `FOR-ROBOTS.md` - entry point for AI agents mining this repo, alpha ranked by transferable value.
- `devlog/2026-07-02.md` - how this release happened.

This is pain #5 from the [family roadmap](https://github.com/Palo-Alto-AI-Research-Lab/claude-bible/blob/main/ROADMAP.md) ("multiple machines, one system"), shipped out of order because the demand signal was loudest.
