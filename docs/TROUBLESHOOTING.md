# Troubleshooting

Common issues hitting `zo build`, `zo init`, `zo draft`, and the agent runtime. Each entry: **Symptom → Cause → Fix**.

If something below doesn't match what you're seeing, check `~/.claude/logs/` and `logs/comms/{date}.jsonl` first — the JSONL trail records every agent decision, gate, and error. Then file an issue with the relevant excerpt.

---

## Sub-agent sessions crash on macOS when the team spawns

**Symptom**
You run `zo build`, the Lead Orchestrator launches in its tmux pane, and as soon as it calls `Agent(team_name=..., name=...)` to spawn the first batch of teammates, sessions start dying — pane closes, "Claude Code crashed", or the whole tmux window vanishes. Sometimes preceded by `fork: Resource temporarily unavailable` or "could not allocate".

**Cause**
This is upstream of ZO. ZO launches **one** Claude Code session in tmux; the Lead inside that session uses Claude Code's native `TeamCreate` + `Agent(...)` to spawn teammates. Each teammate is a **separate Claude Code process tree** (claude main + node + several MCP servers + tool subprocs — typically 10–30 procs each). Spawning 5–7 teammates in parallel can add 100–250 procs in seconds.

macOS enforces a per-UID process cap (`kern.maxprocperuid`, default **2666**). Heavy Electron users (Chrome with many tabs, VSCode, Slack, Discord, Spotify, Docker Desktop) routinely sit at 1500–2000 procs already. Adding the team pushes them over the cap → `fork()` fails → cascading session deaths.

**Specific reproducer: the MNIST demo plan.** `classical_ml` Phase 1 is configured to spawn **5 agents in parallel** (`data-engineer`, `test-engineer`, `research-scout`, `code-reviewer`, `domain-evaluator`) at the very first phase — see [src/zo/\_orchestrator\_phases.py](../src/zo/_orchestrator_phases.py). That's the heaviest spawn burst in any default workflow. If you're hitting the crash specifically on `zo build plans/mnist-digit-classifier.md`, this is the burst doing it. Other workflow modes (`deep_learning`, `research`) and custom plans typically default to 2 agents per phase (`code-reviewer` + `research-scout`), which is far less likely to trip the cap.

**Fix — try in order**

1. **Upgrade Claude Code.** 2.1.119+ shipped two relevant fixes: an agent-teams permission-dialog crash and a 50 MB/hr MCP HTTP buffer leak. If you're on anything older, this might fix it outright.
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   claude --version
   ```

2. **Check your process headroom.**
   ```bash
   ps -U $(whoami) | wc -l        # current process count
   sysctl kern.maxprocperuid       # cap (default 2666)
   ```
   If the first number is >1500, you're at risk. Close heavy Electron apps you don't need (Chrome, Slack, Discord, Docker Desktop, browser tab hoarders).

3. **Raise the cap, persistently.** Default Apple values are conservative.
   ```bash
   sudo sysctl -w kern.maxproc=8000 kern.maxprocperuid=4000   # one-shot
   ```
   To persist across reboots, create `/Library/LaunchDaemons/limit.maxproc.plist` with the values above and `launchctl load -w` it.

4. **Diagnose with `--no-tmux`.** If `zo build --no-tmux` still crashes, the tmux pane is not the culprit — it's the Lead → `Agent(...)` flow itself.
   ```bash
   zo build plans/my-project.md --no-tmux
   ```

5. **Capture the crash for upstream.** Look in `~/Library/Logs/DiagnosticReports/` for crash reports timestamped at the spawn moment, plus `~/.claude/logs/` for the Claude Code session log. File those at https://github.com/anthropics/claude-code/issues — Anthropic engineers can debug from the dump.

---

## Do I need to set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` manually?

**Symptom**
You see this prefix in older docs or example commands and aren't sure if you still need it.

**Cause**
Claude Code's agent teams feature is gated behind that env var. ZO's project-level `.claude/settings.json` already sets it (`"env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }`), so when you `zo build` from inside the ZO repo, Claude Code picks it up automatically — the manual prefix is **redundant but harmless**.

If you `zo build` from a directory without ZO's `.claude/settings.json` (e.g. running against a portable `.zo/` delivery repo on a fresh machine), you may need to either copy the env block into a project-level `.claude/settings.json`, or set the var in your shell rc:
```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

**Note:** prefixing the var on the `zo build` command itself (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 zo build ...`) sets it on the Python process but **does not propagate to the tmux child window** — `tmux new-window` inherits from the tmux server's environment, not from the calling shell. Either rely on `.claude/settings.json` (preferred) or `export` it before starting tmux.

---

## `zo: command not found` after `setup.sh`

**Symptom**
`./setup.sh` reports all checks pass; `zo init my-project` returns `command not found`.

**Cause**
`uv sync` installs the entry-point binary into `.venv/bin/`. If you have conda, pyenv, or system Python active in your shell, `.venv/bin/` is not on `PATH`.

**Fix**
`setup.sh` (Check 11) auto-fixes by symlinking `.venv/bin/zo` → `~/.local/bin/zo` (which `uv install` puts on `PATH`). Re-run:
```bash
./setup.sh
```
If `~/.local/bin` isn't on your `PATH`, add it: `export PATH="$HOME/.local/bin:$PATH"` to your shell rc.

---

## Claude Code session opens blank, prompt never submitted

**Symptom**
`zo build` (or `init`/`draft`) opens a tmux pane with the Claude TUI rendered, but no prompt appears in the input field — the agent just sits idle.

**Cause**
`tmux paste-buffer` is fire-and-forget. On a cold start, Claude Code's TUI takes 5–10 seconds to become input-ready (extensions, hooks, `CLAUDE.md` loading, memory file scan). If the paste lands before the input field is live, the text is dropped silently.

**Fix**
Already mitigated in the wrapper — `_wait_for_tui_ready()` polls `tmux capture-pane` and waits for two consecutive stable readings >100 chars before pasting. If you still hit a blank session, the prompt file is preserved at `logs/wrapper/{team}-prompt.txt` for manual paste:
```bash
cat logs/wrapper/lead-orch-prompt.txt | pbcopy
# focus the Claude pane: Cmd-V, then Enter
```

---

## Build appears stuck — "Monitoring session" with no visible output

**Symptom**
Terminal shows `Monitoring session: pid=XXXXX` and nothing else for minutes.

**Cause**
You launched `zo build` outside of a tmux session, so the wrapper fell back to headless mode (Claude Code with `--print` / `--dangerously-skip-permissions`) which has no TUI. The work is happening, but it's invisible.

**Fix**
Start a tmux session first:
```bash
tmux new -s zo
zo build plans/my-project.md
```
Or watch the headless run live:
```bash
tail -f logs/comms/$(date +%F).jsonl
```

---

## Plan written to a worktree, then `zo build` from main repo can't find it

**Symptom**
`zo draft -p my-project` succeeded; `zo build` from a different shell says "plan not found".

**Cause**
You ran `zo draft` from inside a `git worktree`. ZO writes plans to the **main repo** (not the worktree) so they persist across worktrees and machines.

**Fix**
The plan was written to the main repo's `plans/` directory. From the main repo:
```bash
zo build plans/my-project.md
```
If you're on a different machine, the project state lives in the **delivery repo**'s `.zo/` directory (per PR-028 portable memory). `git pull` in the delivery repo, then `zo continue --repo /path/to/delivery-repo`.

---

## Setup.sh fails silently on macOS bash 3.2

**Symptom**
On a fresh machine, `./setup.sh` exits 0 but no auto-fix happens, even with failures reported.

**Cause**
macOS ships bash 3.2.57 (from 2007). Empty arrays + `set -u` crash silently with "unbound variable". This was fixed by switching to string + integer counter tracking — but if you cloned an old version of ZO, you may still hit it.

**Fix**
Pull the latest:
```bash
git pull origin main
./setup.sh
```

---

## Where to look when something else is wrong

- `logs/comms/{date}.jsonl` — every agent message, decision, gate, error, checkpoint (JSON Lines)
- `memory/{project}/STATE.md` (legacy) or `{delivery-repo}/.zo/memory/STATE.md` — current phase, blockers, last checkpoint
- `memory/{project}/DECISION_LOG.md` — append-only audit trail
- `~/.claude/logs/` — Claude Code's own session logs
- `~/Library/Logs/DiagnosticReports/` — macOS crash reports
- `scripts/validate-docs.sh` — runs 11 cross-file consistency checks; useful when a doc claim seems off

If you find a new failure mode that needs documenting, check `memory/zo-platform/PRIORS.md` for the existing entries and add a new `PR-NNN` following the same format.
