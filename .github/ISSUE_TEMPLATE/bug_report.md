---
name: Bug report
about: Something isn't working as documented
title: ""
labels: bug
assignees: ""
---

## Description

A clear description of what went wrong.

## Steps to reproduce

1. Run `...`
2. ...
3. Observe `...`

## Expected behaviour

What you expected to happen.

## Actual behaviour

What actually happened. Paste error messages, stack traces, or screenshots here.

## Environment

- ZO version: `zo --version`
- Python version: `python --version`
- OS: `uname -a` (or Windows version)
- Claude Code CLI version: `claude --version`
- tmux version: `tmux -V`
- Install method: clone / pip / uv

## Logs

If applicable, attach relevant entries from:

- `logs/comms/{date}.jsonl`
- `memory/{project}/STATE.md`
- `memory/{project}/sessions/`

Please redact any client-identifying content before pasting.

## Have you checked

- [ ] [docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md) for known issues
- [ ] Open issues for duplicates
- [ ] `./scripts/validate-docs.sh` runs clean on your branch
