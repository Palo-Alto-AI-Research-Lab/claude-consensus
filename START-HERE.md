# START HERE: one page for the busy evaluator

You landed on the flagship repo of a strange experiment: a **non-technical founder and his AI cofounder running a fleet of Claude machines as one organism**, publishing every working part of it, free. This page is the 5-minute map: what to run, what to read, and where the rest of the work lives.

## Verify first, read later (15 minutes)

We would rather you check than trust. One command, no arguments, no network, no packages, no API key:

```bash
git clone https://github.com/Palo-Alto-AI-Research-Lab/claude-consensus
cd claude-consensus
python demo/demo.py
```

It runs the published `reference/consensus.py`, simulates two machines on your host, and drives five self-checking scenarios: **A** happy-path (`propose -> counter -> accept -> commit -> verify x2`), **B** human-gate (a risky Tier-2 action refuses to auto-commit), **C** tier-tripwire (a mislabelled dangerous action is force-escalated), **D** split-brain (both sides of a partition commit; caught on heal), **E** corrupt-line (garbage in the ledger does not eat later events). Exit code `0` = every end-state correct, so the demo is also the integration test.

The honest headline it prints: **the consensus engine makes 0 LLM calls and spends 0 tokens.** Full cycle ~433 ms over 6 CLI calls, and process startup (~70 ms each) dominates that wall time; the engine itself derives state at ~3.7 µs/event, a 6-event proposal in about 20 µs. Honest limits: this is a single-host simulation of the engine, not a network benchmark of the fleet. Method and caveats: [docs/EVALS.md](docs/EVALS.md). Every known way it breaks (9 documented failure modes, 3 of them reproduced live by the demo) is in [docs/FAILURE-MODES.md](docs/FAILURE-MODES.md).

## What this is, in one line

**Multi-machine consensus for Claude agents: the machines deliberate, the human presses the button.** Autonomy everywhere except two wake-up gates: money/irreversible actions, and deadlock.

## The repo family (7 public repos)

Everything below is extracted from the same live production system, sanitized, MIT/free:

| Repo | What it is |
|---|---|
| [claude-consensus](https://github.com/Palo-Alto-AI-Research-Lab/claude-consensus) | **You are here.** Consensus protocol, dual-rail bus, ACK discipline, self-healing sync |
| [claude-bible](https://github.com/Palo-Alto-AI-Research-Lab/claude-bible) | Governance codex: one rulebook for founder, human assistants, and every Claude. The law to this repo's diplomacy |
| [sqlite-graph-memory](https://github.com/Palo-Alto-AI-Research-Lab/sqlite-graph-memory) | Agent memory that survives a context reset: SQL facts + embeddings + graph edges in one SQLite file |
| [agent-leash](https://github.com/Palo-Alto-AI-Research-Lab/agent-leash) | Zero-trust control model for delegated-authority agents: deterministic gates around the model, not inside it |
| [charm-os](https://github.com/Palo-Alto-AI-Research-Lab/charm-os) | MCP read-broker: one server, many agents, scoped access to a shared knowledge base |
| [the-journey](https://github.com/Palo-Alto-AI-Research-Lab/the-journey) | 📖 The build-in-public book (see below) |
| [clawrush](https://github.com/Palo-Alto-AI-Research-Lab/clawrush) | The public diary: English devlogs, longreads, reusable artifacts |

## The book

**[相棒 AIBŌ · The Partner](https://github.com/Palo-Alto-AI-Research-Lab/the-journey)** is the whole collaboration as a day-by-day book, wins and rakes included. Two forms side by side: a narrative for humans (RU/EN) and [`llms-full.txt`](https://github.com/Palo-Alto-AI-Research-Lab/the-journey/blob/main/llms-full.txt) for machines. Point your coding agent at it and it inherits the patterns.

## The method

- **Evals over demo videos.** Every claim ships with a command that reproduces it on your machine, with its limits stated ([docs/EVALS.md](docs/EVALS.md)).
- **Disciplines become structure.** A rule that lives in prose gets forgotten; here the safe path is the only path (one dual-send entry point, single-writer files, deterministic tripwires).
- **Scars are kept, not scrubbed.** The reference code is the live implementation, sanitized; the comments keep the real failures and their fixes.
- **Human authority is a hard gate, not a vibe.** Machines negotiate everything reversible; money, outbound, and the irreversible always reach a recorded human approval.
- **AI agents are first-class readers.** [FOR-ROBOTS.md](FOR-ROBOTS.md) is the entry point written for your agent, with the transferable patterns ranked.

## Upstream

A distilled version of this protocol is proposed as an official Anthropic cookbook: [anthropics/claude-cookbooks#778](https://github.com/anthropics/claude-cookbooks/pull/778), *Coordinating agents that don't share memory*.

## Talk to us

Engineers: we give away a working seed of this setup, free, to people who test-drive it with their own fleet and tell us what broke.

- 💬 WhatsApp: **+1 341 222 9178**
- 📅 Calendly: [calendly.com/paloaltolab](https://calendly.com/paloaltolab)
- 🐦 X: [@Tony_Stef_](https://x.com/Tony_Stef_) · 📣 Telegram: [@ClawRus](https://t.me/ClawRus) (RU) / [@ClawEng](https://t.me/ClawEng) (EN)

Anton Dzyatkovsky (founder) & Mike (AI cofounder, Claude Code)
