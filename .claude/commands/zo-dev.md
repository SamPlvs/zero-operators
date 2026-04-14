---
description: Resume building/improving ZO itself — loads full platform context and picks up where we left off
---

# /zo-dev — Continue developing the Zero Operators platform

You are resuming work on the Zero Operators platform itself (not a project ZO is running — the platform code).

## 1. Load context

Read these files in order:

1. `CLAUDE.md` — project rules, coding conventions, self-evolution protocol
2. `memory/zo-platform/STATE.md` — where we are
3. `memory/zo-platform/DECISION_LOG.md` — recent decisions (last 5)
4. `memory/zo-platform/PRIORS.md` — accumulated learnings from failures

## 2. Present briefing

Show the user a concise summary:
- Current state and what's been done
- Known issues
- What's next
- Any priors relevant to the likely next task

## 3. Ask what to work on

After the briefing, ask the user what they'd like to work on. Common tasks:
- **prod-001** — first production project (plan drafting, source docs)
- **Bug fixes** — from the known issues list
- **New features** — agent improvements, CLI enhancements, workflow changes
- **Testing** — running MNIST again, testing a specific mode

## 4. Follow the protocol

Remember the AUTOMATIC Memory & Docs Protocol from CLAUDE.md:
- Update STATE.md on every commit
- Append to DECISION_LOG for every decision
- Add to PRIORS.md if any failure occurs
- Cascade doc updates if public interface changes
- Run self-evolution on any error

This is non-negotiable and automatic — don't wait for the user to ask.
