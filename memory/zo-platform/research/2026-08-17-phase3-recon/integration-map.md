# ZO v2 Phase 3 (WS-C) — Build-Ready Integration Map

Branch: `claude/v2-phase3-substrate` (recon done on `claude/v2-phase2-control-plane` @ 8466d29). Authoritative design source: `plans/zo-v2-rearchitecture.md:107-115` (external checker in the LifecycleWrapper poll loop; NOT a monitor agent; NOT a cron). `specs/watchdog.md` §3.1/§3.4/§3.5/§4/§5 are superseded (see §5, §7).

Line refs re-verified 2026-08-17 where mappers disagreed (see §5). Three ground-truth facts that constrain everything below:

1. **One `zo build` = one lead session = one phase; there is no loop anywhere in cli.py.** `cli.py:1134 get_current_phase` → `:1143 build_lead_prompt` → `:1150 _launch_and_monitor` → `:800 launch_lead_session` → `:920 wait_for_completion` → `:942 orchestrator.end_session()` → `:953 deregister_session` / `:955-957 consolidate_all`. `zo continue` (`cli.py:1206`) is `click_ctx.invoke(build, ...)` at `cli.py:1274`. `Orchestrator.advance_phase` (`orchestrator.py:752`) and `mark_subtask_complete` (`:848`) have **zero runtime callers**; therefore `_auto_iterate_if_needed` (`:1239`), `evaluate_loop_state` call (`:1276`), `_finalize_experiments` (`:1163`), `mark_phase_passed` (`:829`) are all unreachable in production today. Phase 3 supplies the missing driver, it does not replace one.
2. **Two structurally different poll loops.** `_wait_tmux` (`wrapper.py:669-761`, default path via `use_tmux = not no_tmux` `cli.py:798`) has NO pid, NO rate-limit handling, NO stdout log; `_wait_headless` (`wrapper.py:763-822`) has a pid but its rate-limit code is effectively dead (reads only `stdout_log` at `:792`, which under `--print --output-format json` `:436-437` is a single blob at exit) and is a retry loop (`:793-808`).
3. **No process identity anywhere.** tmux `LeadProcess(pid=None, ...)` `wrapper.py:278`; `surrogate._pid_alive` `:279` is bare `os.kill(pid,0)`; `register_session` stores lock-write time as `started_at` `:261`; psutil absent (`pyproject.toml:34-40`); no `pane_pid|pgrep|lstart|etime` anywhere in src.

---

## 1. Watchdog (oracle checks 11–12)

### 1.1 Module boundary

**New `src/zo/watchdog.py`** (pure logic, no subprocess in the classifier path; <500 L):
- `HeartbeatRecord(BaseModel)`: `schema_version:int=1`, `agent_id:str`, `agent_type:str`, `session_id:str`, `pid:int|None`, `process_start_identity:str|None` (tagged `"{platform}:{value}"`, port of OMC `team-owner-epoch.ts:69-112`), `last_tick_at:str` (ISO), `status: Literal["ready","polling","executing","compacting","shutdown"]` (OMC `types.ts:103` + ZO-added `compacting`), `last_event:str`, `progress_marker:str|None` (ledger mtime or last tool_use_id — see §5 "fresh mtime, zero progress").
- `load_heartbeat(path) -> HeartbeatRecord | None` (fail-open, `contracts.py:164-169` shape) BUT the checker converts to a **three-state** `Freshness = fresh|stale|unknown`; `unknown` is never a stall verdict (hazard: `contracts.py:167` inversion; OMC `team-owner-epoch.ts:146-147` "unknown identity is never positive proof of death").
- `NeverBlockReason(StrEnum)`: `context_limit|rate_limit|auth_error|user_abort|compacting|unknown` + `classify_never_block(text_tail: str, *, is_interrupt: bool|None=None) -> NeverBlockReason|None` — pattern tables ported verbatim from OMC `todo-continuation/index.ts:370` (context #213), `:390` (rate #777), `:442` (auth #1308, 16 patterns), `:295` (user abort; bare `interrupt` deliberately excluded per #2478), normalizer `:141`; plus OMC `tmux-detector.ts:34` rate-limit text patterns AND its false-positive layer (`stripGitOutputLines :153`, saved-transcript reject `:70/:74`, new-lines-only cursor `:376-389`). Include MIT attribution comment (`oh-my-claudecode/LICENSE:1-3`).
- `StallVerdict(BaseModel)` modelled on `LoopDecision` (`experiment_loop.py:183-202`, `reason` field for DECISION_LOG, `evaluated_at`).
- `WatchdogState` per-run dataclass (tick count, `nudges_used`, `paused_until`, `last_progress_at`, `last_scan_cursor`, `consecutive_stale`) — reset at top of `wait_for_completion` (hazard `wrapper.py:576-580` ad-hoc self attrs; mapper 5). Persist nudge budget to `<memory_root>/heartbeats/_watchdog.json` so a wrapper restart cannot refill it (OMC `idle-nudge.ts:66` in-memory hole).
- `process_start_identity(pid) -> str|None`: linux `/proc/<pid>/stat` field 22 after last `)`; darwin `ps -o lstart= -p N` under `LC_ALL=C`; validator regex allowlist ≤1024 chars (OMC `team-owner-epoch.ts:112`). `identities_may_match` with darwin `usec=='0'` wildcard (`:128`). `is_process_identity_dead(pid, recorded)` positive-proof-only (`:138-147`); EPERM = alive (ruflo `swarm-tools.ts:85`).
- Consider `src/zo/_proc.py` for `_pid_alive` + start-identity, shared with `surrogate.py` (mapper 1 recommends not importing the private `surrogate._pid_alive`).

**Wrapper owns the tick** (`wrapper.py`): `_watchdog_tick(process, *, pane_text|stdout_tail)` called from both loops; nudge/pause/escalate side effects live here because they need `self._comms`, tmux, and `LeadProcess`.

**Escalation-to-restart lives ABOVE the wrapper** in the new driver (§2) — `kill_session` (`wrapper.py:824-861`) returns a terminal `ERRORED`/`exit_code=-9` LeadProcess by contract (`:836-840`, `:857-861`); do not relaunch inside `_wait_tmux`.

### 1.2 Heartbeat writer (hook side)

- **Handler:** add `"heartbeat": _handle_heartbeat` to `_HANDLERS` (`hookkit.py:382-389`); `main()` fail-open dispatch (`:392-407`, bare except `:402`, `_trace` on both paths `:403/:405`, always return 0) gives fail-open for free.
- **Wiring:** append a SECOND object to the `PostToolUse` array in `.claude/settings.json:74` (currently only `Write|Edit` → `cascade-reminder.sh` `:74-85`) with matcher `"*"` (or `""`) → `bash .claude/hooks/zo-hookkit.sh heartbeat 2>/dev/null || exit 0`, timeout 5. Do not touch the Write|Edit entry. Also call the same writer from `_handle_subagent_stop` (`hookkit.py:120`, wired `:103-114`) and `_handle_precompact` (`:233`, wired `:115-127`, write `status="compacting"`) and Stop/`drift-guard` (`:196`, wired `:86-102`).
- **Identity:** new `_agent_identity(data) -> (agent_type, agent_id)`; do NOT change `_agent_name` (`hookkit.py:112-117`, contract lookup at `:355-356` depends on it). Evidence: `agent_id`+`agent_type` present in SubagentStop (11/57 lines, `logs/hook-trace-2026-08-12.jsonl:3,:57`) and PostToolUseFailure (`:55`, `hook-trace-2026-08-17.jsonl` last line); ABSENT in all 34/34 PreToolUse `sealed-paths` traces. PostToolUse identity is unverified (not routed today) — first commit ships the handler as trace-only, run one live session, read `stdin_keys` (same method as `DECISION_LOG.md:1261`). Filename key = `agent_id` when present, else `session_id` namespaced (`lead-<session_id>.json`).
- **Path:** `<memory_root>/heartbeats/<agent_id>.json` where memory_root = `hookkit._memory_root(repo_root)` (`hookkit.py:64-69`: `$ZO_MEMORY_ROOT` → `<repo_root>/memory/zo-platform` if dir → None; `repo_root` = `$ZO_REPO_ROOT` else cwd `:60-61`). Return early on None (pattern `:236`, `:260`). Write via `ledger._atomic_write` (`ledger.py:81-91`).
- **Perf:** move `from zo.contracts import ...` (`hookkit.py:34`) lazy into the handlers that need it (style at `:226,:238,:262`); debounce: skip write if existing mtime < 2 s old.
- **Env for hooks:** `ZO_REPO_ROOT` (shim `.claude/hooks/zo-hookkit.sh:29`), `ZO_MEMORY_ROOT/ZO_DELIVERY_ROOT/ZO_CONTRACTS_PATH` (`cli.py:1076-1078` → `_launch_and_monitor(extra_env=)` `cli.py:1163` → `launch_lead_session` `wrapper.py:143-151` → tmux inline prefix `:230-231` / headless `env.update` `:456-463`). Add `ZO_SESSION_ID` (comms session id minted `cli.py:1059`/`:1094`) so heartbeat ↔ comms correlate.
- **Gitignore + sealing (same PR, before first write):** `memory/zo-platform/heartbeats/` is currently TRACKED (`.gitignore:33-34` re-includes `memory/zo-platform/`; `git check-ignore` matched only `logs/heartbeats/x.json` via `.gitignore:27`) — add `memory/zo-platform/heartbeats/`, and also `memory/zo-platform/contracts.json` + `plan-ledger.json` (`contracts.py:10` docstring "gitignored" is false for the platform root). Add `"heartbeats"` to `_SEALED_DEFAULTS` (`hookkit.py:47-50`; prefix match `:340-342` seals the subtree) so agents cannot forge liveness via Write/Edit; hook-internal python writes never traverse PreToolUse (`.claude/settings.json:63-72` matcher `Write|Edit`, handler `hookkit.py:328-379` reads `tool_input.file_path`).
- **Shim scope constraint:** `.claude/hooks/zo-hookkit.sh:21` `[[ -d "$REPO_ROOT/src/zo" ]] || exit 0` — heartbeats exist only for sessions whose `.claude/` is the platform repo's. Holds today because lead is launched `cwd=str(zo_root)` (`cli.py:801`, `--add-dir` `wrapper.py:226`); no hooks are scaffolded into delivery repos (`scaffold.py` has none). Assert as a Phase-3 invariant with a test; fresh-context builders (§2) MUST also be launched with `cwd=zo_root` + `ZO_MEMORY_ROOT`.
- **Non-build sessions:** report (`cli.py:3491`), init-architect (`:2002`), draft (`:3168`) call `_launch_and_monitor` without `extra_env` → no `ZO_MEMORY_ROOT` → hookkit falls back to platform root. Document heartbeats as build/continue-only, or set env inside `_launch_and_monitor` from `delivery_repo`.

### 1.3 External checker insertion points (both loops)

**tmux (`_wait_tmux` `wrapper.py:669-761`):**
- Insert `self._watchdog_tick(...)` at **line 712**, immediately after `self._check_gate_mode_change()` (`:710`) and `self._maybe_open_training_pane()` (`:711`), BEFORE liveness reads `:713-714`. NOT after `:749` — the suspected-dead branch `:741-745` calls `on_status`, sleeps `min(poll_interval, _DEAD_RECHECK_INTERVAL)` (`:744`) and `continue`s (`:745`), skipping the timeout check `:754`. Regression test: watchdog fires on a poll that takes the `:745` path.
- Hoist ONE `pane_text = self._capture_tmux_pane(pane_id, lines=200)` per poll (def `:998`, default 50; today only 5 lines and only inside `if on_status:` `:749-752`) and share with `on_status` — otherwise 4 subprocess spawns/poll (`_tmux_pane_alive :920-931` does `list-panes -a`; `_tmux_claude_running :934-960` display-message).
- Available per-poll: `pane_exists`(713), `claude_running`(714), `poll_count`(706/716), `consecutive_dead`(707), `start_time=time.monotonic()`(702), `process.started_at`(279). Debounce constants `_STARTUP_GRACE_POLLS=2 :74`, `_DEAD_CONFIRM_POLLS=2 :78`, `_DEAD_RECHECK_INTERVAL=2.0 :81`, rationale docstring `:677-701` — reuse for stall confirmation, don't add a second debounce.
- Do NOT let the watchdog inherit `_tmux_claude_running` semantics (`:947-960` compares `#{pane_current_command}` to a shell set `:959-960`; true for any non-shell foreground; may flip to `bash` during long Bash tool calls — see open Q).

**headless (`_wait_headless` `wrapper.py:763-822`):**
- Insert at **line 778** (after `_check_gate_mode_change()` `:777`, before `rc = self._proc.poll()` `:779`).
- Never-block classification runs between `:792` (`output = self._read_tail(process.stdout_log)`) and `:793` (`if self._detect_rate_limit(output)`), i.e. BEFORE any backoff decision. Read `stderr_log` too (`:453/:455`, never read today); track a byte cursor rather than re-tailing 100 lines (`_read_tail :1029-1037`) — otherwise a single `429` re-matches forever and `retries` never resets (`:808`).
- Fix `self._proc` init: assigned only at `:287` (None, tmux) and `:474` (headless); `__init__` `:83-99` never sets it → `AttributeError` on any fresh `LifecycleWrapper.wait_for_completion(reconstructed_process)` (the restart pattern) at `:779` and `kill_session :847`. Add `self._proc: subprocess.Popen | None = None` next to `:99`. Tests only pass because they set `wrapper._proc` by hand (`tests/unit/test_wrapper.py:468,488,510,531`).

**Shared:** factor `_poll_tick(process, *, pane_text, stdout_tail)` used by both loops (parity already broken: `_wait_headless` never calls `_maybe_open_training_pane`, passes `""` to `on_status` `:813`). `wait_for_completion` (`:547`, `poll_interval=10.0 :551`, `timeout=None :552`) gains keyword-only `watchdog: WatchdogConfig|None`, `memory_root: Path|None`; stash alongside `:574-578` inside the same `try/finally` (`:585-586`, teardown mirrors `_close_training_pane :636-646`). Only production caller `cli.py:920` passes on_status/gate_mode_file/project_name/delivery_repo — thread `memory_root` explicitly (do not derive from `gate_mode_file.parent`, `cli.py:1159`).

**Timeout accounting:** `timeout` is `time.monotonic() - start_time` since `:702/:772` — a rate-limit pause would count against it (`:754`). Track `last_progress_at` separately and exclude paused intervals.

### 1.4 Never-block taxonomy — detection sources

| Reason | tmux source | headless source | Hook/feed source |
|---|---|---|---|
| rate_limit | pane tail (last N lines, cursor-tracked) w/ OMC patterns + git-strip | stderr/stdout tail via cursor | — |
| context_limit | pane tail (`context low`/compact banner) | stdout json envelope + transcript % estimate (OMC `persistent-mode/index.ts:1003-1008`) | PreCompact → `status=compacting` heartbeat |
| auth_error | pane tail | stderr tail | — |
| user_abort | — | rc + `is_interrupt` | `PostToolUseFailure.is_interrupt` (present in every live trace `logs/hook-trace-2026-08-12.jsonl:40,55`) — currently DROPPED by `_handle_post_tool_failure` `hookkit.py:287-308`; add `is_interrupt`, `agent_id`, `agent_type`, `never_block_reason` to the failure-feed record (`:294-302`, file `<ZO_FAILURE_FEED_DIR|repo_root/logs/comms>/failures-<date>.jsonl`, live records `logs/comms/failures-2026-08-17.jsonl`) |
| thinking-only streak | — | — | Stop payload `transcript_path` (`hookkit.py:197,205-207`); extend `_last_assistant_text` (`hookkit.py:153`) into a port of OMC `classifyLastAssistantTurn` (`persistent-mode/index.ts:1513-1607`, streak max 3, TTL 5 min `:1479-1481`, fail-open) |

Rules: taxonomy runs FIRST in the tick, before any nudge (tmux: a rate-limited TUI still shows `claude` as foreground → looks RUNNING forever until `timeout :754`; naive watchdog at 712 would nudge it — the exact check-11 failure). Do NOT reuse `_RATE_LIMIT_PATTERNS` (`wrapper.py:51-56`, bare `r"429"` at `:52`, matcher `:894-896`) against pane text (`0.4291`, `step 4290`). Ambiguous → do not nudge. Bypass order ported from OMC `persistent-mode/index.ts:2268-2373`.

### 1.5 Nudge mechanism + budget

- **tmux only.** Extract `_paste_and_submit(pane_id, text)` from `_launch_tmux :255-270` (`load-buffer :256`, `paste-buffer -t :260`, `sleep(1) :266`, `send-keys Enter :267-270`; retry variant `_verify_prompt_submitted :364-398`). Use a **named buffer** (`tmux load-buffer -b zo-nudge -` from stdin; `paste-buffer -b zo-nudge -d`) so the operator's paste buffer isn't clobbered and no temp file is needed.
- **Headless cannot be nudged**: `Popen(cmd, stdout=fh, stderr=fh, text=True, env=env)` `:462-463` inherits parent stdin; prompt is one-shot argv `-p` `:450` under `--print` `:436`. Ladder = stale-heartbeat → `kill_session :824` → fresh relaunch with re-derived prompt (§2).
- **Budget** (port OMC `idle-nudge.ts:29-131`): `delay 30 s` dwell before first nudge, `max 3` per agent per run, `scan throttle 5 s`, idle timer resets after each successful nudge, message "Continue working on your assigned task and report concrete progress (not ACK-only)". Predicate = heartbeat stale AND (positive process death OR zero progress-delta over N ticks) AND never-block reason is None. Never nudge the lead pane while `paused_until` is set. Persist `nudges_used` (§1.1). Exhaustion → `AgentStatus.STALLED` returned from `wait_for_completion` → driver escalates to iteration restart (`_record_learning` `orchestrator.py:1323` so stalls become priors). Model on `_maybe_open_training_pane :588-634` (fires once, sentinel `self._training_pane_id = ""` `:632/:634`, torn down in `finally`).
- Global backstop: an un-raisable hard cap on total nudges + restarts per run (OMC `security-config.ts:44-108`: overrides may only lower).

### 1.6 Rate-limit wait-and-resume (both modes)

- Replace `:793-808` retry loop (`_backoff_wait :898-900` = `30*2^n + U(0,5)`, `_max_retries=3 :89/:96`, terminal `RATE_LIMITED :795`) with a **paused state evaluated each poll**: `while time.monotonic() < resume_at: tick(); sleep(min(poll_interval, remaining))` — never a single blocking `time.sleep(wait_secs)` `:807` (kills `on_status`, timeout, gate-mode re-read, and watchdog for 30–120 s).
- Reset-time source, in order: (1) parse `resets? .+ at` / `resets at HH:MM` from the matched tail; (2) poll-until-clear with an injectable clock + injectable `is_still_limited` probe (edge-triggered: `was_limited and not now_limited and not degraded`, OMC `daemon.ts:305`; 30 s per-probe timeout `:360`); (3) fallback existing backoff. No OAuth usage API (`rate-limit-monitor.ts:19-58`) dependency.
- Add `AgentStatus.PAUSED_RATE_LIMIT`, `STALLED`, `RESTARTED` (`_wrapper_models.py:15-23`); `LeadProcess` gains `pid_start_identity`, `nudges_used`, `paused_until`, real `pid` in tmux (`:26-37`). `cli.py:926` compares `== "completed"` (StrEnum-safe); handle new members before the generic else `:924-928` and BEFORE teardown `:930-960`.
- tmux coverage: same paused state, text from hoisted pane capture.
- Resume must be **verified**: require heartbeat delta or ledger delta within a bounded window after resume, else mark resume failed (OMC's `sendResumeSequence` `tmux-detector.ts:414-434` returns true unverified).
- Existing tests asserting retry semantics must be rewritten: `tests/unit/test_wrapper.py:504` `test_detects_rate_limit_and_backs_off`, `:525` `test_rate_limit_exhausts_retries`.

### 1.7 PID + start-time identity

- tmux: capture `#{pane_pid}` after pane creation (`:214-219`) — that is the shell pid (claude typed via send-keys `:239-242`); resolve claude child via `pgrep -P <shell_pid>` (one hop, poll until present during `_wait_for_tui_ready :304-350`); store `pid` + `process_start_identity` on `LeadProcess`.
- headless: `pid=proc.pid` `:466`; add identity at `:465-469`.
- Fix `surrogate.register_session` (`:240-268`) to also store `proc_start`; `sweep_locks :293-311` and `live_sessions :314-321` compare the tuple (recycled pid today keeps a dead lock alive → blocks consolidation `cli.py:763,949-958`). ruflo reconcile-on-every-load pattern (`swarm-tools.ts:107-149`) as hygiene; 24 h TTL only as legacy-record fallback.
- No psutil (`pyproject.toml:34`; adding it requires `uv.lock` regen or `.github/workflows/ci.yml:41` fails). Use `ps -o lstart=` (darwin) / `/proc` (linux, CI `ci.yml:26-28` ubuntu, py 3.11/3.12).

### 1.8 Config threading

- `ProjectConfig` (`project_config.py:28-51`) has no `model_config` → `watchdog:` block silently dropped, and `save_project_config :132-152` round-trips `model_dump()` (data loss). Add nested `watchdog: WatchdogConfig = WatchdogConfig()` (`enabled`, `poll_interval_sec`, `stall_threshold_min` — reconcile spec's 20 (`specs/watchdog.md:65`) vs check-11's 10-min stall, `nudge_delay_sec`, `nudge_budget`, `hard_max_restarts`, `rate_limit_probe_timeout_sec`); drop `tick_cron`/`reroute` from `specs/watchdog.md:60-70`.
- `ProjectContext.make_target` (`cli.py:75-87`) loads then discards ProjectConfig; add `make_project_config()` (None for legacy layout `cli.py:88`; legacy default = enabled with hardcoded defaults). Precedence via a `resolve_policy`-style merge (`experiment_loop.py:136-180`: CLI > plan > clamp > default). Thread `cli.py:1071` → `_launch_and_monitor` (new kwarg, sig `:709-731`) → `wait_for_completion :920`. `--low-token` preset (`cli.py:262-269`) gains a sessions cap key.

### 1.9 Comms logging

Five event types only (`comms.py:31-38`); do NOT add a sixth. Use `self._comms.log_checkpoint(agent="watchdog", phase="lifecycle", subtask="heartbeat|nudge|rate-limit-pause|rate-limit-resume|escalate", progress=..., blockers=[reason])` (`comms.py:381-416`) and `log_error(agent="watchdog", error_type="stall", severity="warning"|"blocking", description=..., escalated_to=...)` (`:344-379`, severity vocab `:61-67`). Both render live in `_print_status` (`cli.py:869-913`: checkpoint `:904`, error `:908`; `message` events NOT rendered — add branch only if needed). Files: `zo_root/logs/comms/<date>.jsonl` under `fcntl.flock` (`comms.py:200-209`). Also `_trace`-style JSONL of tick decisions (`hookkit.py:81-96` shape) so check-11 can assert on a log line. Every escalation → `DecisionEntry` (`orchestrator.py:1279-1288` pattern) + `_record_learning` (`:1294-1302`).

---

## 2. Fresh-context loop (check 13, Linux later)

### 2.1 The seam
`cli.py:1134-1166`. Split `_launch_and_monitor` (`:709-960`) into `_launch_once` (`:798-939`: register-per-attempt `:789-794`, launch `:800`, wait `:920`, status print) and once-per-run teardown (`:942` end_session, `:944` semantic.close, `:953-957` deregister+consolidate; permissions overlay reclaim `:773-783` once). New driver `zo.driver.run_phase_loop(...)` (or `experiment_loop.run_fresh_context_loop`; keep `experiment_loop.py` pure — `__all__ :56` is decision-only, 16 pure tests) called from `build`:

```
while (phase := orch.get_current_phase()) is not None:
    orch._refresh_gate_mode()            # gate_mode may change mid-run (orchestrator.py:729)
    zo_contracts.set_active_phase(memory_root, phase.phase_id)   # contracts.py:172 — today only on GATED (orchestrator.py:789)
    assert no RUNNING exp for phase (or _finalize/_abort first)  # orchestrator.py:1388 mint side-effect
    prompt = orch.build_lead_prompt(phase) + ledger digest section
    process = _launch_once(prompt, ...)   # headless claude -p, fresh context
    if process.status in {STALLED, ...}: restarts += 1; check hard cap; continue
    ev = orch.advance_phase(phase.phase_id)          # FIRST runtime caller ever
    if ev.requires_human / phase GATED: print nonce (prepare_gate_review orchestrator.py:902-904); break
    if ev.decision == ITERATE and phase is phase_4: git checkpoint; iterations += 1; check caps; continue
```
Break cleanly on mid-loop switch to SUPERVISED (`_auto_iterate_if_needed` returns None `:1258-1259`). `_consume_gate_decision` (`:403-427`) applies only at decompose — mid-loop approvals need an explicit re-check.

### 2.2 Inputs & producers (all re-derived from disk)
- Ledger entry/digest: `load_ledger` `ledger.py:93`, `summarize :248`; written by `_emit_plan_ledger` `orchestrator.py:363-396` (merge-preserving `ledger.py:125-170`). New `_prompt_ledger_digest()` section in `build_lead_prompt` list `orchestrator.py:541-554` (iteration N-of-M banner).
- Experiment lineage: `ExperimentRegistry.lineage :233`, `render_checklist :287-321` (auto-refreshed via `_safe_refresh_checklist :343-354`); active/parent exp via `_ensure_experiment_for_phase :1124-1161` (idempotent on RUNNING `:1150-1152`; parent = `latest_in_phase :1154` regardless of status).
- Priors digest: `_prompt_memory :1784-1805` (priors[:8] `:1798`, semantic top_k=3 on `plan.objective` `:1801` — consider querying with current hypothesis).
- `next.md`/`diagnosis.md`/`result.md`: written by model-builder agent (`.claude/agents/model-builder.md:68-79`), read from disk per prompt at `orchestrator.py:1483-1492`. NOT produced by Python; `parse_next_md :650`/`parse_hypothesis_md :636` have zero prod callers → `Experiment.hypothesis`/`next_ideas` always empty → DEAD_END (`experiment_loop.py:303-319`, `check_dead_end :395`) is dead code. Wire both parsers into `_finalize_experiments :1163` (`:1220-1226`).
- Ledger write-through per iteration: `record_attempt` at iteration start (`ledger.py:227`), only oracle path calls `mark_phase_passed :184`; `reset_phase :203` on CONTINUE (`orchestrator.py:1312-1315`) — `attempts` is the only monotonic per-subtask signal.

### 2.3 Spawn mechanism
Reuse `_launch_headless` (`wrapper.py:414-461`: `[claude, --print, --output-format, json, --model, M, --max-turns, N, --add-dir, cwd]` `:427-441`, `_resolve_claude_bin :904`, env `os.environ.copy()+extra_env :456-459`, Popen to log files `:461-463`, LeadProcess w/ pid `:465-469`). Improvements from ruflo `headless-worker-executor.ts:1397-1431`: prompt on **stdin** (`child.stdin.end(prompt)`; argv `-p` at `wrapper.py:450` risks tokenization/ARG_MAX), `start_new_session=True` + kill process group (SIGTERM → SIGKILL after 5 s) because `claude --print` spawns grandchildren; hard per-iteration timeout. `--dangerously-skip-permissions` only works with `--print` (PRIORS PR-001 `memory/zo-platform/PRIORS.md:16-23`) — confirm `permissions_overlay.py` + sealed-paths hook are honored in `--print` mode (open Q). Do NOT copy `_generate_session_summary` (`cli.py:686-696`: bare `"claude"`, no env/cwd, `except Exception: pass`). `cwd=zo_root` + `ZO_MEMORY_ROOT/ZO_DELIVERY_ROOT/ZO_REPO_ROOT` mandatory (§1.2 shim constraint; sealing depends on it).

### 2.4 Git checkpoint
`surrogate.commit_worktree(path, *, message)` (`:360`, `add -A` + commit, True only if a commit was made) over `_git :97-101` — the only git subprocess code in ZO (precedent `consolidate.py:174-182`; `orchestrator.py`, `cli.py`, `scaffold.py` have none). Call after `advance_phase` returns ITERATE (i.e., after `reset_phase` at `orchestrator.py:1312`), message `zo: checkpoint {exp.id} ({verdict})`; then update `SessionState.git_head` (`_memory_models.py:40`, verified by `recover_session` `memory.py:287-301`) so the fresh session doesn't raise a git_head mismatch blocker. Scope question: `add -A` may commit weights (delivery `.gitignore` scaffolded `scaffold.py:227`) — prefer `.zo/experiments/` + artifacts allowlist. Fix `Experiment.artifacts_dir` absolute path (`experiments.py:491`, docstring `:176-178` says relative; consumers `orchestrator.py:1203`, `experiments.py:448,455`) — a check-13 blocker if `registry.json` is committed and checked out on the Linux box.

### 2.5 Caps
`LoopPolicy` (`experiment_loop.py:113-118`: max_iterations 10, plateau_epsilon .01, plateau_runs 3, stop_on_tier must_pass, dead_end .9), low-token clamps `:130-133` applied in `resolve_policy :166-177` (CLI > plan > clamp > default `:149-150`); budget enforced at `:261` by counting COMPLETE exps (durable). Driver MUST also enforce max_iterations + `hard_max_restarts` as a session counter (a session that never reaches a gate never consults the evaluator). Never mutate the returned policy — `resolve_policy` returns the shared `DEFAULT_POLICY` singleton (`:178-179`, model not frozen `:120`). Plateau requires exact metric-name match (`experiments.py:515-525`) and `len(deltas)==plateau_runs` (`experiment_loop.py:283`) — log missing deltas.

### 2.6 Prompt text changes
- `.claude/agents/lead-orchestrator.md`: no Phase-4 loop content (grep hits only `:23,:175,:216,:230`). Add: one-iteration-per-session rule; `specs/watchdog.md:77` liveness-by-evidence rule; STATE.md → plan-ledger.json at `:101,:213,:230`.
- `.claude/agents/model-builder.md:86-110` already disk-based; add "no prior-iteration context survives"; reconcile `:290` (escalate after 2 non-improving iterations) with loop-owned plateau (`experiment_loop.py:274-296`).
- `orchestrator.py` mirrors: `_render_loop_briefing :1456-1519`, `_prompt_experiment_context :1378-1454`, `_prompt_coordination :1809-1838` (add nothing about heartbeats — hook-driven by design).

### 2.7 Testable on Mac vs Linux-only
- Mac (mock spawn): driver loop with a fake `launch_lead_session`/`_launch_once` returning scripted `LeadProcess` statuses; assert `advance_phase` invoked (first runtime caller — wiring test), restart cap, gate break, git checkpoint via `commit_worktree` on a tmp git repo, prompt digest content, ledger `record_attempt` per iteration, `set_active_phase` per iteration. Reuse `tests/integration/test_auto_iteration.py:154-162` `_run_iteration` as the executable contract.
- Linux-only: real `claude -p` spawn, `--print` permissions behavior, check 13 (GPU demo ≥ 91.62%, cost ≤ 1.15×; `plans/zo-v2-rearchitecture.md:60,114-115`). Preflight `_check_claude_cli` (`preflight.py:84-89`, wired `:70`) is `shutil.which` only — strengthen with `claude --version` (pattern `_check_docker :187-199`). Land loop behind an off-by-default flag; STATE.md records "11-12 green, 13 pending".

---

## 3. Deferrals

### 3.1 `evaluate_loop_state` ledger input
Signature `experiment_loop.py:205-209` `(registry, phase, policy=None)`; body reads only `registry.experiments` `:230-233`. **Add keyword-only `*, ledger: LedgerFile | None = None`** appended after `policy`. Call-site count: **16 in `tests/unit/test_experiment_loop.py`** (lines 102,111,122,137,145,150,159,176,185,196,218,232,243,259,312,328; 12 pass policy positionally) + 1 prod (`orchestrator.py:1276`, lazy-import block `:1265-1269`) + `test_auto_iteration.py:162` indirect. Zero churn. At `:1276` pass `ledger=zo_ledger.load_ledger(self._memory.memory_root / LEDGER_FILENAME)` (`ledger.py:93` fail-open None; `LEDGER_FILENAME :51`). Ledger has no oracle_tier (`LedgerFile :67-74`, `LedgerEntry :54-64`) — ledger contributes `phase_status`/`passes`/`attempts` only; registry stays for tiers. Add one test: ledger=None → identical verdict.

### 3.2 Session-restore cutover (STATE.md → plan-ledger.json)
- **Precedence: ledger > STATE.md, per-phase, presence-based**; comms warning on per-phase mismatch. Preserve GATED > ACTIVE > PENDING-deps-met, BLOCKED excluded — lives in `get_current_phase` `orchestrator.py:687-727` (`:709-712`, `:713-716`, `:717-726`, docstring `:704-705`) reading only `phase.status` → **no change**; nine `TestGetCurrentPhase` tests (`tests/unit/test_orchestrator.py:463-566`) are source-agnostic and remain the oracle. Rationale `PRIORS.md:1089-1150` (PR-037 rules `:1125,:1143,:1148`).
- **PR-036 preserved by moving validation**: reuse `_VALID_PHASE_STATUSES` (`_memory_formats.py:30-32`; enforcement `:154-168`, error shape `:158-165`) in a validated `LedgerFile.phase_status` field (`ledger.py:73`) and in `set_phase_status :239-245`; strict-load variant for restore: file exists + parse fails → raise with path/phase/value/valid list; file absent → fall back to STATE.md (`load_ledger :93-98` fail-open stays for hooks). Drift-guard test twin of `tests/unit/test_memory.py:156`. Note `memory.read_state` swallows `(ValueError, KeyError)` at `memory.py:139` (untested; PR-036 error never reaches operators) — fix on the restore path.
- **Schema gap**: no per-subtask completion in ledger (`passes` phase-wide, `mark_phase_passed :184-200`; `record_attempt :227-236` ≠ complete). Add `LedgerEntry.completed: bool` + `mark_subtask_completed(memory_root, phase_id, subtask)`, called from `mark_subtask_complete` `orchestrator.py:858` next to `record_attempt`; `reset_phase :203-213` must clear it (mirrors `completed_subtasks.clear()` `orchestrator.py:953,1311`). Guard: `tests/unit/test_orchestrator.py:1049 test_partial_progress_restored`. Keep oracle-owned `passes` separate (anti-Goodhart).
- **Cutover site**: `_restore_phase_states` `orchestrator.py:468-481` (`:478` is the PR-036 traceback line — keep coercion after boundary validation). Also `orchestrator.py:359-360` (session `phase` pointer gated on STATE.md `phase_states` emptiness) and `start_session :237-256`.
- **Write-through audit** (writers): present at `orchestrator.py:792` (GATED), `:829` (COMPLETED), `:946` (PROCEED), `:954-956` (ITERATE), `:960` (ESCALATE/blocked), `:1312-1315` (loop CONTINUE); **missing** at `:962` (HOLD → GATED; add `_ledger_safe("set_phase_status", pid, "gated")`) and `:476-481` (restore, no write-back). `_ledger_safe :398-401` discards `_mutate`'s False (`ledger.py:173-181`) — log it. Ordering hazard: `decompose_plan :350-353` runs `_consume_gate_decision :351` before `_emit_plan_ledger :353` — first-run gate decision drops into `doc is None` (`ledger.py:176-178`); reorder or ensure ledger exists. `emit_ledger :144-148` prev_status always wins → after cutover STATE.md hand-edits are inert (open Q).
- STATE.md keeps being written (`_capture_phase_states :293-303` from `end_session :284`) as human projection — required by `hookkit.py:236,:260`, `cli.py:2303-2309` (`zo status` exits 1 without STATE.md — relax to either file), `cli.py:1081-1082` (mode derivation from `state.phase`).
- Tests: keep `test_real_resume_via_state_md_round_trip` (`test_orchestrator.py:568-605`) + add ledger twin + conflict test (ledger wins). Two-orchestrators-one-MemoryManager pattern `:940-987`. Also SKIPPED never written / `pending` never re-set (`_orchestrator_models.py:36`; `ledger.py:198,211,239`); subtask_id slug collision `ledger.py:153,77-78`.

---

## 4. Reusable existing code (deduped)
- `ledger._atomic_write` `ledger.py:81-91`, `_mutate :173-181`, `load_ledger :93-98`, `summarize :248-254`, `emit_ledger` merge `:136-148`, `record_attempt :227`, `reset_phase :203`, `mark_phase_passed :184`, `set_phase_status :239`.
- `contracts.emit_contracts` atomic pattern `contracts.py:151-161`, `load_contracts :164-169`, `set_active_phase :172`.
- `hookkit._memory_root :64-69`, `_repo_root :60`, `_trace :81-96`, `main :392-407`, `_agent_name :112-117`, `_last_assistant_text :153`, `_sealed_prefixes :314-348`, `_SEALED_DEFAULTS :47-50`, `_handle_post_tool_failure :287-308`.
- `wrapper._check_gate_mode_change :648-667` (per-poll file-watch, log-on-change), `_maybe_open_training_pane :588-634`, debounce consts `:74-81` + docstring `:677-701`, `_launch_headless :414-461`, `_resolve_claude_bin :904`, `_capture_tmux_pane :998`, `_read_tail :1029`, `_tmux_pane_alive :920`, `_tmux_claude_running :934`, paste/submit `:255-270` + `_verify_prompt_submitted :364-398`, `kill_session :824-861`, `monitor_team :481-497` / `read_task_list :499-512` / `_read_team_config :1011-1026` (secondary signal only; `is_active` True when `tasks_total==0` `:496`).
- `surrogate._pid_alive :279-290`, `register_session :240-268`, `sweep_locks :293-311`, `live_sessions :314-321`, `_git :97-101`, `commit_worktree :360`.
- `comms.log_checkpoint :381-416`, `log_error :344-379`, `_write_event` flock `:200-209`; `_print_status` renderer `cli.py:869-913`.
- `experiment_loop.LoopDecision :183-202`, verdict cascade `:227-283`, `resolve_policy :136-180`; `orchestrator._ledger_safe :398-401`, `_record_learning :1323`, DecisionEntry-per-verdict `:1279-1288`, `_refresh_gate_mode :729`; `experiments.render_checklist :287-321`, `lineage :233`, `save_registry :269-279`.
- `training_display._time_ago :92-105`; `memory.write_state :142-161`, `_append_locked :178`, `_get_git_head :303`; `preflight._check_docker :187-199`; `cli.py:2317-2352` ledger-first status table; `cli.py:2912-2967` `watch-training` external poll loop; `_peers_live` fail-open guard `cli.py:747-796`.
- Test harness: `tests/unit/test_wrapper.py:28-46` fixtures, `:543-641` class-patched staticmethods + `side_effect` scripts + `timeout=-1`, `:504-541` headless harness, `:729-744` parametrized classifier; `tests/unit/test_hookkit.py:31-36 _run`, `:39-58`; `tests/integration/test_hooks_shim.py:29-38 _run_shim`, `:41-66 contracts_env`, `:113-146 TestSettingsWiring`; `tests/unit/test_ledger.py:36-52 _workflow`, `:140-157` sealed deny; `tests/unit/test_orchestrator.py:53-72` fixtures; `tests/unit/test_experiment_loop.py:62-92 _exp/_registry`; `tests/integration/test_auto_iteration.py:154-162`.
- Reference ports (MIT): OMC `types.ts:103`, `heartbeat.ts:19-81`, `idle-nudge.ts:29-131`, `persistent-mode/index.ts:1479-1607, 2268-2373, 1003`, `todo-continuation/index.ts:141,295,370,390,442`, `tmux-detector.ts:34,70,74,153,376`, `daemon.ts:305,345,360,405-433`, `team-owner-epoch.ts:29-148`, `security-config.ts:44-151`; ruflo `swarm-tools.ts:80-149`, `repo-supervisor.ts:20-124`, `headless-worker-executor.ts:1378-1431`; ralph `ralph.sh:84-113`, `CLAUDE.md:7-104`.

---

## 5. Hazards & conflicts between mappers (resolved)
| Conflict | Resolution (verified by grep 2026-08-17) |
|---|---|
| `_check_gate_mode_change()` in `_wait_tmux` at 710 (m1,m3,m6) vs 723 (m5) | **710** (`_maybe_open_training_pane()` 711); `_wait_headless` twin at 777 |
| `_maybe_open_training_pane` def 588 vs 592; `_capture_tmux_pane` def 997 vs 998; `poll_interval` 551 vs 554 | **588 / 998 / 551** (`timeout` 552) |
| cli teardown: `end_session` 942 vs 947; deregister 949-958 vs 953-957 | **942**; deregister **953**, consolidate **955-957**; launch **800**, wait **920** |
| Rate-limit sleep 806 vs 807, retries 807 vs 808 | **807 / 808**; RATE_LIMITED 795, `_detect_rate_limit` def 894, `_backoff_wait` 898-900 |
| `self._proc` init hazard (m1) | Confirmed: only assigned at 287 and 474; `__init__` 83-99 has none |
| psutil acceptable (m2 suggests) vs absent (m1,m5,m6) | Absent (`pyproject.toml:34`); use `ps`/`/proc` |
| `evaluate_loop_state` test sites: 15+ / ~20 (DECISION_LOG:1277) / 16 | **16**, all in `test_experiment_loop.py` |
| PID identity attributed to ruflo (digest) | Wrong — OMC `team-owner-epoch.ts:69-148`; ruflo has signal-0 only |
| OMC fresh-spawn per phase | Does not exist; autopilot blocks Stop in-session (`persistent-mode/index.ts:2556-2564`); fresh-spawn precedents are ralph.sh:95 + ruflo headless executor |
| Heartbeat root git status | `memory/zo-platform/heartbeats/` TRACKED (`.gitignore:33-34`); only `logs/` ignored (`:27`) — fix .gitignore first |
| `DECISION_LOG.md:1265` "PostToolUseFailure did not fire for nonzero-exit Bash" | Contradicted by `logs/comms/failures-2026-08-17.jsonl` — correct the entry |
| specs/watchdog.md cron/orchestrator-owned tick (`:40,:74-79`) vs plan | Plan wins (`plans/zo-v2-rearchitecture.md:107-114`); rewrite spec in-PR |
| `_agent_name` "verified against live payloads" (STATE.md:11) | Only for SubagentStop/PostToolUseFailure; PreToolUse 34/34 no identity → sealed-paths off-limits branch (`hookkit.py:351-368`) likely never fired in prod |
| Heartbeat freshness alone = liveness (OMC `heartbeat.ts:81`) | Insufficient — no write during long tool calls (`mcp-team-bridge.ts:746`); require stale AND (dead OR no progress) |
| Sentinel completion grep (ralph.sh:99) | Unsound; use ledger predicate + per-subtask attempt cap |
| `Experiment.artifacts_dir` absolute path | Check-13 blocker if registry.json crosses machines |

Additional hazards to carry: `_wait_tmux` `timeout` includes paused time (`:754`); `on_status`-gated pane capture (`:749-752`); tmux nudge clobbers global paste buffer (`:255-258`); `_ensure_experiment_for_phase` mint side effect on prompt build (`orchestrator.py:1388`); STATE.md flushed only at `end_session` (`:284`) — ledger is the crash-safe source; `apply_human_decision` nonce single-use (`:928-942`) — driver must break on GATED; `hookkit._trace` cwd fallback lets tests write into real repo (`test_hookkit.py:353-359` `explode` pollution) — new tests must `monkeypatch.setenv` both `ZO_REPO_ROOT` and `ZO_MEMORY_ROOT`; PostToolUse `*` hook cost (bash+python+pydantic import per tool call).

---

## 6. Test plan skeleton
Conventions: module docstring naming workstream + checks (`tests/unit/test_ledger.py:1-6`, `test_contracts.py:1-4`), two-tests-per-mechanism rule (`test_hookkit.py:1-8`), section comments `# ---- <mech> (oracle check N) ----` (`test_hookkit.py:61,108,186,245,274`), class docstring stating both halves (`test_ledger.py:137-138`), test names containing "seeded" (`test_hookkit.py:65,139,278`; `test_ledger.py:143`; `test_plan.py:751`).

**`tests/unit/test_watchdog.py`** — "Tests for zo.watchdog — the WS-C execution substrate (plan oracle checks 11-12)."
- `# ---- never-block taxonomy (oracle check 11, negative half) ----`: parametrized positives per category (pattern `test_wrapper.py:729-744`) + negatives (`0.4291`, `step 4290`, git log line "fix weekly report", cat'ed old transcript) + `is_interrupt` → user_abort.
- `# ---- stall predicate ----`: three-state freshness; unknown → no verdict; stale+dead → stall; stale+progress-delta → no stall; startup grace.
- `# ---- process identity ----`: mocked `subprocess.run` for `ps`/`/proc` read; darwin usec wildcard; malformed → not dead; EPERM alive.
- `# ---- nudge budget ----`: dwell, max 3, throttle, timer reset, persisted budget survives re-instantiation, exhaustion → STALLED.
- `# ---- rate-limit pause/resume (oracle check 12) ----`: injectable clock + probe; edge-triggered resume; degraded ≠ clear; resume verified by heartbeat delta; timeout excludes pause.

**`tests/unit/test_wrapper.py` additions** (fixtures `:28-46`; `@mock.patch("zo.wrapper.time.sleep")`; class-patch `_tmux_pane_alive/_tmux_claude_running/_capture_tmux_pane/_kill_tmux_window`; instance-patch `monitor_team`; `timeout=-1` or scripted dead sequence; call_count assertions):
- **Seeded stall (check 11)** on `_wait_tmux`: heartbeat file mtime aged via injected clock, pane text neutral → nudge called ≤3 → STALLED within one poll iteration after threshold; assert comms `log_error(error_type="stall")` line.
- **Rate-limited NOT nudged (check 11)** on `_wait_tmux`: pane text contains OMC rate-limit banner → nudge mock never called, status PAUSED, then resume on probe flip.
- Same pair on `_wait_headless` (harness `:504-541`); rewrite `:504` and `:525`.
- Watchdog fires on the `:745` continue path; `_proc` default None; single pane capture per poll shared with `on_status`.

**`tests/unit/test_hookkit.py` additions**: `heartbeat` handler writes atomic JSON keyed by `agent_id`/`session_id`, `compacting` on precompact, fail-open with unset memory root; `_handle_post_tool_failure` record carries `is_interrupt/agent_id/agent_type/never_block_reason`; heartbeats sealed (`test_ledger.py:140-157` pattern).

**`tests/integration/test_hooks_shim.py`**: extend `TestSettingsWiring.test_all_ws_a_events_wired` (`:117-146`) with `heartbeat` on PostToolUse; **new wiring test** asserting `_watchdog_tick` is invoked from both poll loops (grep-free: patch and assert called). `test_hooks_shim.py::_run_shim` (`:29-38`) end-to-end heartbeat write with `ZO_MEMORY_ROOT` in tmp.

**Driver / fresh-context** (`tests/integration/test_fresh_context_loop.py`): fake `_launch_once`; assert `advance_phase` called (first runtime caller), restart cap, GATED break with nonce, git checkpoint on tmp repo via `commit_worktree`, `set_active_phase` per iteration, `record_attempt` per iteration, no RUNNING exp reuse (`orchestrator.py:1388` guard), gate-mode re-read.

**Deferrals**: `evaluate_loop_state(..., ledger=None)` unchanged verdict + ledger-aware case; ledger validator PR-036 triple (`test_memory.py:156,163,184` twins), strict-load raises on corrupt existing file, ledger round-trip resume twin of `test_orchestrator.py:568-605`, ledger-wins conflict, HOLD write-through, `mark_subtask_completed`/`reset_phase` clear, first-run gate decision lands in ledger, `zo status` without STATE.md.

**Config**: `WatchdogConfig` round-trip through `save_project_config`, legacy default, precedence.

---

## 7. Docs/memory cascade
- `specs/watchdog.md`: `:3` Status RFC→implemented; `:39-40` §3.1 cron→poll loop; `:53-58` §3.4; `:60-70` §3.5 config keys; `:74-79` §4 → `wrapper.py` `_wait_tmux :669`/`_wait_headless :763`, delete `:79` monitor-agent line; `:83-88` §5 → checks 11-12; `:92-93` "spec-only" false. Reconcile 20-min default (`:65`) vs 10-min check.
- `specs/workflow.md:547` Subtask 4.3 fresh-context semantics; `specs/memory.md:286,:291`; `specs/comms.md:48` untouched (no new event type); `specs/agents.md` untouched (no new agent).
- `plans/zo-v2-rearchitecture.md:67,:132` and `docs/reference/v2-rearchitecture.mdx:99` "854" (real count 917 → post-Phase-3 recount); mdx `:65-66` no Status column (decide: add to all five tables `:44,:63,:78,:92` or prose `:87-103`); `docs/roadmap.mdx:30`; `docs/COMMANDS.md:13` only if `zo watchdog` ships; `docs/cli/build.mdx:133` if headless full builds become supported.
- `README.md:13` badge (`tests-854`), `:529` ("780 platform tests"), `:307` slash count only if a `.claude/commands/*.md` is added (validate-docs Check 3 HARD FAIL `scripts/validate-docs.sh:110-129` with `STATE.md:65`). Checks 1/2/7 (`:46-103,:215-222`) fire only on new agent file; Check 4 (`:136-148`) on version bump; Check 6 (`:192-208`) warn-only, already tripping (diff 63); Check 8 inert locally (`:244`).
- `.gitignore` (heartbeats/, contracts.json, plan-ledger.json under memory/zo-platform); `contracts.py:10` docstring; `.claude/agents/lead-orchestrator.md:101,:213,:230` + Phase-4 section; `.claude/agents/model-builder.md:86-110,:290`; `pyproject.toml`/`uv.lock` only if a dep is added.
- Memory: `memory/zo-platform/STATE.md:9-11` (prepend Session 041 "pick up here", demote 040; front-matter `:3-7`); `DECISION_LOG.md` append EOF (`:7-14` template): watchdog RFC-vs-plan divergence, `evaluate_loop_state` keyword-only choice, mdx status-column decision, correction of `:1265`; `PRIORS.md` only on real failure (`:1057-1101` template, "+ 7 skipped" = `tests/unit/test_semantic.py:451`, not e2e — `tests/e2e/` has zero .py); `memory/zo-platform/sessions/session-041-<date>.md` (`session-040-2026-08-12.md:1-3,:92` shape, mandatory "## Next session — pick up here").

---

## 8. Open questions for Sam (build-changing only)
1. **tmux nudge semantics mid-turn**: `paste-buffer`+Enter into a BUSY Claude TUI (only launch-time uses exist, `wrapper.py:255-270,386-398`) — queued as next turn, swallowed, or interrupt? Determines whether nudges are safe to repeat (budget 3) or must be single-shot → restart.
2. **Heartbeat write source**: is PostToolUse `*` acceptable (process spawn per tool call), or must a second source (pane-text delta / comms mtime) cover thinking / long single tool calls? And does PostToolUse carry `agent_id` (unverified — trace-only first commit resolves it).
3. **Rate-limit reset time**: is a `resets at` timestamp visible in the TUI banner / stderr, or does check 12 accept poll-until-clear with injectable probe (deterministic in tests, no OAuth API)?
4. **Heartbeat root**: `ZO_MEMORY_ROOT` = delivery `.zo/memory` (`cli.py:69,1076`) vs platform `zo_root` for comms/hook-trace (`cli.py:1096`, `hookkit.py:94`). One root or both threaded through `wait_for_completion`?
5. **Driver ownership + scope**: new `zo.driver` module vs orchestrator method; wire the FULL `advance_phase` gate path (`orchestrator.py:797,830-832` pytest/notebook/snapshot per iteration) or only the phase_4 loop branch? And how do subtasks get marked complete in prod (`mark_subtask_complete :848` has no caller → `advance_phase` always ITERATE "Subtasks remaining" `:838-844`)?
6. **Per-agent vs lead-only liveness**: wrapper tracks one `LeadProcess`; teammates are files only (`monitor_team :481-497`, no pids). Phase 3 = lead process identity + hook heartbeats for teammates?
7. **STATE.md hand-edit semantics after cutover**: ledger wins silently / with warning / refuse-to-start? (prod-001 fix workflow in PR-036/037 edits STATE.md.)
8. **`--dangerously-skip-permissions` for fresh builders**: is `permissions_overlay.py` + sealed-paths honored under `--print`? If not, the fresh loop voids Phase-1 enforcement.
9. **Linux demo mode for check 13**: headless end-to-end (contradicts `docs/cli/build.mdx:133`) or tmux lead spawning headless children? Also: is registry.json/absolute `artifacts_dir` crossing machines (fix becomes a blocker)?
10. **Git checkpoint scope**: whole delivery tree (`add -A`) or `.zo/experiments/` + artifacts allowlist?