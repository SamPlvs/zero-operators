# Watchdog / Heartbeat — anti-stall for long-running autonomous runs

**Status:** implemented (v2 Phase 3 / WS-C, PR-A). Plan oracle checks 11–12 (`plans/zo-v2-rearchitecture.md`).
**Owner:** wrapper (`src/zo/wrapper.py`) + pure policy module (`src/zo/watchdog.py`).
**Motivation:** a real failure mode observed in a long autonomous run — the whole team stalled *silently for ~38 hours* and nobody noticed until the human asked "where are we?".

> **Divergence from the original RFC (read this first).** The first draft of
> this spec proposed a *cron-scheduled self-invoke tick* owned by the
> orchestrator agent, with a nudge → respawn → reroute remediation ladder.
> `plans/zo-v2-rearchitecture.md` (Phase 3, "Watchdog first") supersedes that:
> the tick is an **external checker in the LifecycleWrapper poll loop** — a
> Python process that is *not* an LLM, so it cannot itself stall, hallucinate
> liveness, or be killed by the session it watches. Sections 3–6 below describe
> what shipped. Section 1 (the failure mode) and section 2 (requirements) are
> unchanged; requirement 1 ("active heartbeat, not passive wait") is now met by
> the poll loop rather than by cron.

---

## 1. The failure mode

ZO's lead-orchestrator is **event-driven**: it acts when it receives a message (from the human or from a teammate agent). This is efficient, but it has a silent-death hole:

- When every teammate agent finishes its immediate task and goes **idle** (or dies silently), no teammate message is emitted.
- The orchestrator therefore receives **no wake signal**, so it is never re-invoked.
- A long **background job** (a training run, a sweep, an external CI/deploy) emits no agent message while it runs — and if its launcher dies, nothing reports it.
- Net: "wait for the next message" silently degrades into **"do nothing, indefinitely."** The run looks alive (no error) but has flat-lined.

Contributing factors seen in the wild:
- A dedicated monitor agent (a "context-warden") is itself a single point of failure — it can die silently too, taking the only liveness check with it.
- No-news is read as progress. Absence of an error is not evidence of forward motion.

This is distinct from context-window saturation (already handled by checkpoint→respawn). This is **idle-stall**: healthy-looking agents that have simply stopped moving the work forward.

---

## 2. Requirements

1. **Active heartbeat, not passive wait.** The run must have a wake source that fires on a wall-clock schedule independent of teammate messages, so an all-idle team cannot go unnoticed.
2. **Liveness by evidence, not by silence.** Detect progress from observable state (process is running, output files/heartbeats advancing), never from "no bad message arrived."
3. **Auto-remediation.** On a detected stall, re-mobilize (nudge the responsible session) rather than only alerting — but never fight a stop the platform itself imposed.
4. **No single point of failure.** The checker is owned by the run's Python wrapper, not by one killable monitor agent.
5. **Survives session boundaries.** Nudge budgets and pause state are persisted on disk so a wrapper restart cannot refill them; the *policy* lives in `.zo/config.yaml` so a fresh session re-establishes the watch automatically.
6. **Cheap + quiet.** No LLM calls; only speaks (comms events) when it detects a stall, a pause, a resume, or an escalation — never on every tick.

---

## 3. Design (as implemented)

### 3.1 The tick — external checker in the wrapper poll loop
`LifecycleWrapper.wait_for_completion(..., watchdog=, memory_root=, zo_session_id=)` builds a `WatchdogRunner` (`src/zo/_wrapper_watchdog.py`) when `watchdog.enabled` and a memory root are given. Both poll loops call `_watchdog_tick(process, text=…, can_nudge=…)` once per iteration:

- **tmux** (`_wait_tmux`, the default): one `capture-pane` per poll (last 200 lines) feeds the never-block classifier and the progress digest; `can_nudge=pane_ready_for_nudge(text)` — an idle prompt is nudgeable, a busy pane (spinner, "esc to interrupt", dialog) is not, so a stall behind a hung tool call escalates after `escalate_grace_sec` instead of returning NUDGE forever. The tick runs *before* the liveness reads, so it also fires on the "suspected dead, re-check" path.
- **headless** (`_wait_headless`, `--no-tmux`): a byte cursor over the stdout/stderr logs (rolling 16 KB window); `can_nudge=False` (the `--print` prompt is one-shot argv, there is nothing to type into).

The tick runs `zo.watchdog.evaluate()` — a pure, clock-injected function — and the wrapper performs the side effects. Every tick appends one JSONL line to `<memory_root>/heartbeats/_watchdog-ticks.jsonl` (`ts, action, stalled, reason, never_block, progress`) and persists `WatchdogState` to `<memory_root>/heartbeats/_watchdog.json` (both fail-open).

### 3.2 Liveness by evidence — four observers
`evaluate()` receives `progress: bool`, computed by four observers that each return True only on **new** evidence (`zo.watchdog.observe_*` + the runner's CPU sampler):

- **Heartbeats** — hook-written JSON per agent at `<memory_root>/heartbeats/<agent_key>.json` (`HeartbeatRecord`; writer is `zo.hookkit._handle_heartbeat` → `zo._hook_heartbeat.stamp_heartbeat`, wired to `PostToolUse` `*` and stamped from Stop / SubagentStop / PreCompact / SessionEnd). Progress = any key's `tick_count` advanced past what the run has seen; files that pre-date the run are baselined and do not count. Freshness is three-state (`fresh|stale|unknown`); **unknown is never a stall verdict**.
- **Terminal text** — `progress_digest()` = SHA-1 of the pane/log text with spinner glyphs, elapsed counters, token counts, and the idle prompt stripped, so UI churn is not progress. Digest changes during a rate-limit pause are *not* progress (the banner itself churns).
- **Files** — mtime advance / appearance of `plan-ledger.json`, the comms log dir, `<delivery>/.zo/experiments`, plus `WatchdogConfig.progress_paths`. Directories are watched one level deep (a *new* entry counts; an in-place append to a nested file does not bump the parent), so point `progress_paths` at the file that actually grows — a training log or metrics file — when a long tool call is expected.
- **Process-tree CPU time** (`zo._proc.process_tree_cpu_seconds`, `ps -A -o pid=,ppid=,time=`) — the lead's tree burning ≥ 25 % of the wall time between two samples (`CPU_BUSY_FRACTION`) is positive activity: a 40-minute `python train.py` inside one silent Bash call is *working*, not stalled, even though heartbeats (PostToolUse-only) and text are quiet. An idle TUI redraws at ~1 % and does not count; a blocked MCP/network call burns nothing and still stalls. Requires a resolved lead pid (`Popen.pid` headless; the filtered `pgrep` child in tmux).

**Process identity** (`zo._proc`, re-exported by `zo.watchdog`): `pid_alive` (ESRCH → dead, EPERM → alive), `process_start_identity` (`/proc/<pid>/stat` field 22 on Linux, `ps -o lstart=` on macOS), `is_process_dead(pid, recorded_identity)` — **positive proof only**: a recycled pid (identity mismatch) is dead, anything unknown is *not*. tmux resolves the claude child via `pgrep -n -P <pane_pid> -f claude` (newest child whose command line mentions claude — a shell's prompt helper or gitstatusd is never mistaken for the lead; no match → unknown); headless uses `Popen.pid`. Observed progress contradicts a dead verdict (progress wins), and positive-proof death is escalated **once per run**, not once per stall.

A **stall** = `process_dead is True` OR `now − last_progress_at ≥ stall_threshold_sec`, evaluated only after `startup_grace_sec` and only when no never-block reason applies.

### 3.3 Never-block taxonomy — stops that are never fought
Before any stall decision the tick classifies the last 60 non-empty lines of terminal text (`classify_never_block`, precedence order):

| Reason | Meaning | Watchdog behaviour |
|---|---|---|
| `user_abort` | Ctrl-C / `is_interrupt` / "⎿ Interrupted by user" / "⎿ Interrupted · What should Claude do instead?" | never nudge |
| `context_limit` | context full / prompt too long / compaction banner | never nudge; may escalate after `stall_threshold_sec` |
| `rate_limit` | three tiers: **banner** ("You've hit your usage limit · resets at 3pm", `weekly … limit`, `quota exceeded`, `too many requests`, 429 *with* rate/limit vocabulary, `rate_limit_error`, …), **prose** ("rate limit" in running text), **loose** ("limit reached", "try again later", "hit … limit", "resets … at", "5-hour" — only when the SAME line carries rate/usage/quota/request/API vocabulary; "patience limit reached at epoch 30" is not a banner). All three **pause** (§3.5), never nudge; only banner/parsed-reset evidence classifies an *exit* as `RATE_LIMITED` |
| `auth_error` | `authentication_error`, "please run /login", 401/403 *with* auth vocabulary | never nudge; may escalate after `stall_threshold_sec` |
| `awaiting_input` | permission / question dialogs ("Do you want to proceed? ❯ 1. Yes", "esc to cancel") | never nudge (a nudge would answer the dialog) |
| `compacting` | a heartbeat with `status=compacting` inside the last 5 min | counts as progress; resets the stall clock |

Pattern tables live in `zo._watchdog_text` (ported from oh-my-claudecode under MIT, with contract-specific tightening: no bare `429`, no bare `overloaded`, bare `interrupt` excluded, git-log/diff lines and saved-transcript `cat …` commands stripped first). Ambiguous → do not nudge.

### 3.4 Remediation policy — nudge (bounded) → escalate
1. **Nudge** (tmux only). After a stall persists for `nudge_delay_sec`, paste `nudge_message` into the lead pane via a **named** tmux buffer (`_paste_and_submit`) and press Enter — but only if `pane_ready_for_nudge(text)`: idle prompt visible, no active task, no permission dialog. Budget: `nudge_budget` per run (default 3), `nudge_delay_sec` between nudges; both persisted in `_watchdog.json`. Each nudge logs a comms `checkpoint(agent="watchdog", subtask="nudge")`; a skipped nudge logs `subtask="nudge-skipped"`.
2. **Escalate** — once per stall — when the budget is exhausted, or nudging is impossible (headless, or a tmux pane that stays busy / in a dialog) and `escalate_grace_sec` has passed, or the process is positively dead (once per run): comms `error(agent="watchdog", error_type="stall", severity="blocking", escalated_to="human")`, `LeadProcess.stalled=True`. Headless additionally `kill_session`s the lead (`kill_headless_on_escalate`) because there is no other lever; tmux keeps the human-facing pane alive and lets the loop end naturally. The wrapper returns `AgentStatus.STALLED`; the CLI prints "Session stalled — watchdog escalated".
3. **Respawn / reroute** — *deferred* to the fresh-context driver (PR-B, plan check 13), which consumes `STALLED` and `hard_max_restarts`. The wrapper never relaunches inside its own poll loop.
4. **Never silently truncate**: first stall detection logs a `warning` error event; every escalation is a `blocking` error event; every tick is traced to `_watchdog-ticks.jsonl`.

### 3.5 Rate-limit wait-and-resume (check 12)
On `rate_limit`: enter a **pause** (`AgentStatus.PAUSED_RATE_LIMIT`, `paused_until` = parsed reset time + 15 s slack via `parse_rate_limit_reset` — "resets at 3pm", "resets at 14:30", "try again in 5 minutes", "retry-after: 90", ISO timestamps; the newest banner in the transcript wins — else exponential backoff `rate_limit_backoff_base_sec · 2^attempt` capped at `rate_limit_backoff_max_sec`). Banner clock times are the operator's **local** time (Claude Code renders the reset in local time): the runner passes `tz=local_tz()` (`LifecycleWrapper(tz=…)` / `WatchdogRunner(tz=…)` are injectable) — parsing "resets at 3pm" as 15:00 UTC would push a US/Pacific reset to tomorrow. A parsed reset further away than `rate_limit_max_pause_sec` (a stale clock time that rolled over to tomorrow) is not honoured; backoff applies. While paused the loop keeps polling (never one long `sleep`); paused time is excluded from the run timeout **until an escalation raised during the pause** (resume unverified / max pause exceeded) — after the hand-off the wall clock counts again.

The real TUI never clears the usage-limit line, so "banner gone" is defined by evidence, not by pixels: once `paused_until` has passed, a banner whose rate-limit lines are **unchanged since the pause began** (`WatchdogState.pause_banner_key`) is *stale* and treated as gone — tmux sends up to `resume_nudge_budget` resume nudges, headless waits for evidence; a banner with *new* rate-limit lines is fresh and extends the pause (a real later reset is honoured, a re-printed past time falls back to backoff). A resume is **verified** only by real progress (heartbeat / file / CPU delta) — with the banner still on screen once the reset has passed, or any time once it is gone → `AgentStatus.RUNNING`, `pause_total_sec` accumulated, comms `rate-limit-resume`; the resolved banner (`spent_banner_key`) is ignored until it scrolls out of the 60-line tail, so it cannot re-pause the run. Progress while the banner is fresh and the reset still ahead does not resume (no PAUSE/RESUME flapping). Exceeding `rate_limit_max_pause_sec` escalates. If the process exits while a pause is open the wrapper returns `RATE_LIMITED` with `resume_at` **only with corroboration** — a parsed reset time (`resume_at` set), an unambiguous banner, or a non-zero exit code; a session that finished normally after *mentioning* rate limits stays `COMPLETED`. The CLI prints "rerun `zo continue` after".

### 3.6 Configuration (`.zo/config.yaml` → `ProjectConfig.watchdog`, model `zo.watchdog.WatchdogConfig`)
```yaml
watchdog:
  enabled: true
  stall_threshold_sec: 1200        # 20 min; check 11 tests use 600
  startup_grace_sec: 120
  nudge_enabled: true              # tmux only; pane-ready guard always applies
  nudge_delay_sec: 30              # dwell before first nudge and between nudges
  nudge_budget: 3                  # per run, persisted
  nudge_message: "Continue working on your assigned task and report concrete progress (not ACK-only)."
  resume_nudge_budget: 2
  escalate_grace_sec: 120
  kill_headless_on_escalate: true  # only after evidence says idle (see §3.2 CPU observer)
  rate_limit_backoff_base_sec: 60
  rate_limit_backoff_max_sec: 1800
  rate_limit_max_pause_sec: 21600  # 6 h
  hard_max_restarts: 3             # consumed by the PR-B driver
  progress_paths: []               # extra files/dirs whose mtime advance is progress (name the file that grows, e.g. a training log)
```
The block is strict (unknown keys inside `watchdog:` are a validation error); `ProjectConfig` itself ignores unknown *top-level* keys so legacy configs load. Legacy `targets/*.target.md` projects have no config → defaults (ON). Precedence: `--no-watchdog` > env (`ZO_WATCHDOG=0` kill switch, `ZO_WATCHDOG_STALL_SEC=N`) > `.zo/config.yaml` > defaults (`resolve_watchdog_config`).

---

## 4. Integration points (real files)
- **`src/zo/watchdog.py`** — pure policy: `classify_never_block`, `evaluate(…, tz=)`, observers, persistence, `compute_pause_until`; re-exports `zo._watchdog_models` (`HeartbeatRecord`, `WatchdogConfig`, `WatchdogState`, `StallAction`, `StallVerdict`, `resolve_watchdog_config`), `zo._watchdog_text` (patterns, `rate_limit_match`, `rate_limit_banner_key`) and `zo._proc` (identity, `process_tree_cpu_seconds`).
- **`src/zo/_wrapper_watchdog.py`** — `WatchdogRunner` (config + state + memory root + clock + tz + evidence paths + CPU probe; `tick`, `record_nudge`, `paused_seconds` (capped at an in-pause escalation), `rate_limit_exit_evidence`, `parsed_resume_at`, per-tick JSONL trace).
- **`src/zo/wrapper.py`** — `wait_for_completion(watchdog=, memory_root=, zo_session_id=)`, `_watchdog_tick` from `_wait_tmux` and `_wait_headless`, `_paste_and_submit`, pid + start-identity capture; `src/zo/_wrapper_models.py` — `AgentStatus.PAUSED_RATE_LIMIT`, `STALLED`; `LeadProcess.pid_start_identity/nudges_used/stalled/paused_until/resume_at/pause_total_sec`.
- **`src/zo/hookkit.py`** + **`src/zo/_hook_heartbeat.py`** — `_handle_heartbeat` resolves the memory root and delegates to `stamp_heartbeat` (stdlib-only writer, debounced, atomic), stamped from PostToolUse `*` (`.claude/settings.json`), Stop, SubagentStop, PreCompact, SessionEnd; `heartbeats/` is in `_SEALED_DEFAULTS` so agents cannot forge liveness via Write/Edit; `.gitignore` covers `memory/zo-platform/heartbeats/`, the zo-dir scaffold / `zo migrate` `.zo/.gitignore` covers `memory/heartbeats/` + `memory/plan-ledger.json` + `memory/contracts.json`, and `LifecycleWrapper._start_watchdog` idempotently appends `memory/heartbeats/` to an existing `.zo/.gitignore` so runtime files never enter delivery history.
- **`src/zo/project_config.py`** — `ProjectConfig.watchdog: WatchdogConfig` (round-trips through `save_project_config`).
- **`src/zo/cli.py`** — `ProjectContext.make_project_config()`, `_resolve_watchdog`, `--no-watchdog` on `build`/`continue`, `ZO_SESSION_ID` exported to hooks, `_launch_and_monitor(watchdog=, memory_root=, zo_session_id=)`, `_print_session_outcome` for `STALLED` / `RATE_LIMITED`.
- **`src/zo/comms.py`** — no new event types: `checkpoint(agent="watchdog", subtask=nudge|nudge-skipped|rate-limit-pause|rate-limit-resume)` and `error(error_type="stall")`, both rendered live by `_print_status`.
- **Not touched by design:** `orchestrator.py` (no orchestrator-owned tick), `.claude/agents/lead-orchestrator.md` liveness rule stays advisory prose, `surrogate.py` (identity fix deferred).

---

## 5. Acceptance / tests (checks 11–12)
- `tests/unit/test_watchdog.py` — taxonomy positives/negatives/precedence, `parse_rate_limit_reset`, three-state freshness, `evaluate()` scenario table with an injected clock (seeded 10-minute stall → `NUDGE`×3 → `ESCALATE` once; rate-limited never nudged; pause → resume-nudge → verified `RESUME`; headless resume requires progress; `process_dead` → escalate; startup grace; awaiting-input never nudged; compacting resets the clock; each observer), process identity (Linux `/proc` parse, macOS `ps`, EPERM alive, recycled pid dead, unknown not dead), persistence round-trips, `resolve_watchdog_config` kill switch.
- `tests/unit/test_wrapper.py` — `test_seeded_10min_stall_detected_and_escalated_within_one_poll` (check 11), `test_seeded_rate_limited_session_is_never_nudged` (check 11), `test_seeded_rate_limit_pause_auto_resumes_on_reset` + `test_seeded_static_banner_resumes_at_reset_without_rollover` (check 12), the same trio on the headless harness plus `test_seeded_silent_training_with_busy_cpu_is_not_killed`, `test_busy_pane_never_sends_keys_and_escalates_after_grace`, `test_paused_seconds_stops_accruing_at_escalation`, `test_tz_threads_into_banner_parse`, `test_watchdog_tick_runs_on_suspected_dead_path`, `test_single_pane_capture_per_poll`, `test_permission_dialog_is_never_nudged`, `test_paste_and_submit_uses_named_buffer`, `test_watchdog_disabled_when_config_off_or_no_memory_root`.
- `tests/unit/test_hookkit.py` + `tests/integration/test_hooks_shim.py` — heartbeat written keyed by `agent_id` / `lead-<session_id>`, validates as `HeartbeatRecord`, tick_count increments, debounce, status per event, fail-open without a memory root, heartbeats sealed (seeded Write → deny), settings.json PostToolUse entry asserted, shim end-to-end.
- `tests/unit/test_project_config.py::TestWatchdogConfigThreading` — round-trip, legacy defaults, unknown top-level key ignored, seeded typo rejected. `tests/unit/test_cli.py::TestWatchdogCliThreading` — `--no-watchdog` / config / env reach the launch as `enabled=False`, default path passes config + memory root + session id, `_launch_and_monitor` forwards keyword args to `wait_for_completion`, `STALLED` / `RATE_LIMITED` messages.

---

## 6. Scope boundaries
- **In:** stall detection, bounded nudges, rate-limit pause/resume, escalation, per-tick trace, config threading — all inside one `zo build` session.
- **Deferred to PR-B (fresh-context driver, check 13):** acting on `STALLED` / `RATE_LIMITED` above the wrapper (relaunch with a re-derived prompt, `hard_max_restarts`), and the `surrogate.py` pid + start-time identity fix.
- **Not planned:** an LLM monitor agent, a cron tick, respawn/reroute inside the poll loop, psutil, new comms event types.
- Context-window saturation handling (checkpoint→respawn) is unchanged — this feature covers **idle-stall**, the orthogonal hole.
