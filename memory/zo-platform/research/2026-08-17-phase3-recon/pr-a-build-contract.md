# PR-A build contract — Watchdog (v2 Phase 3 / WS-C, oracle checks 11–12)

Companion to `integration-map.md` (same directory). The map says WHERE; this
contract says WHAT. Builders follow this contract exactly; the map supplies the
exact `file:line` anchors. Where the two disagree, this contract wins.

Ground rules (from CLAUDE.md + plan anti-scope): Python 3.11+, PEP8, type hints,
Google docstrings, files < 500 lines, functions < 50 lines, ruff clean on
`src/`; every mechanism ships WIRED with a seeded-failure test; fail-open for
advisory paths (heartbeats, logging), never for control decisions; no psutil
(stdlib + `ps` / `/proc`); no new comms event types; control-plane files under
the existing per-project memory root only. Ported OMC code carries an MIT
attribution comment (`oh-my-claudecode/LICENSE`, © 2025 Yeachan Heo).

---

## 0. File ownership (disjoint per builder)

| Builder | Owns (create/edit) | Must not touch |
|---|---|---|
| **core** | `src/zo/watchdog.py` (new), `tests/unit/test_watchdog.py` (new) | everything else |
| **wrapper** | `src/zo/wrapper.py`, `src/zo/_wrapper_models.py`, `tests/unit/test_wrapper.py` | hookkit, cli, config |
| **hooks** | `src/zo/hookkit.py`, `.claude/hooks/zo-hookkit.sh`, `.claude/settings.json`, `.gitignore`, `tests/unit/test_hookkit.py`, `tests/integration/test_hooks_shim.py` | wrapper, cli, config |
| **config-cli-docs** | `src/zo/project_config.py`, `src/zo/cli.py`, `tests/unit/test_project_config.py`, `tests/unit/test_cli.py`, `specs/watchdog.md`, `docs/reference/v2-rearchitecture.mdx`, `docs/roadmap.mdx` (only if it names the watchdog as pending), `plans/zo-v2-rearchitecture.md` (check-11 wording only if needed) | wrapper, hookkit, watchdog.py |
| **integrator** (later) | anything, to reconcile | — |

`src/zo/watchdog.py` is the shared dependency: builders wrapper/hooks/config
import it and MUST use the API below verbatim (names, signatures, semantics).

---

## 1. `zo.watchdog` public API (builder: core)

Module docstring: "Watchdog — WS-C execution substrate (plan oracle checks
11-12). Pure logic: no I/O in the classifier and predicate paths; process
identity and file helpers are small, injectable, and fail-open."

```python
SCHEMA_VERSION = 1
HEARTBEATS_DIRNAME = "heartbeats"          # <memory_root>/heartbeats/
WATCHDOG_STATE_FILENAME = "_watchdog.json" # <memory_root>/heartbeats/_watchdog.json
HEARTBEAT_STALE_SWEEP_SEC = 24 * 3600

class HeartbeatStatus(StrEnum):
    READY = "ready"            # turn ended / idle at prompt (Stop hook)
    EXECUTING = "executing"    # tool activity (PostToolUse)
    COMPACTING = "compacting"  # PreCompact
    SHUTDOWN = "shutdown"      # SubagentStop / SessionEnd for that key

class HeartbeatRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    agent_key: str                 # filename stem: agent_id or f"lead-{session_id}"
    agent_id: str | None = None
    agent_type: str | None = None
    session_id: str                # Claude Code session_id from the hook payload
    zo_session_id: str | None = None   # from env ZO_SESSION_ID (comms correlation)
    pid: int | None = None
    process_start_identity: str | None = None
    last_tick_at: datetime         # tz-aware UTC
    status: HeartbeatStatus = HeartbeatStatus.EXECUTING
    last_event: str = ""           # hook_event_name or tool_name
    tick_count: int = 0

def heartbeat_path(memory_root: Path, agent_key: str) -> Path
def load_heartbeat(path: Path) -> HeartbeatRecord | None          # fail-open (None on any error)
def load_all_heartbeats(memory_root: Path) -> list[HeartbeatRecord]  # ignores _watchdog.json + unparsable
def write_heartbeat(memory_root: Path, record: HeartbeatRecord) -> Path   # atomic tmp+os.replace; mkdir -p
def sweep_stale_heartbeats(memory_root: Path, *, now: datetime, older_than_sec: int = HEARTBEAT_STALE_SWEEP_SEC) -> int

class Freshness(StrEnum):  FRESH = "fresh"; STALE = "stale"; UNKNOWN = "unknown"
def classify_freshness(record: HeartbeatRecord | None, *, now: datetime, stale_after_sec: float) -> Freshness
    # None → UNKNOWN; naive datetimes → treat as UTC; UNKNOWN is never a stall verdict.

class NeverBlockReason(StrEnum):
    USER_ABORT = "user_abort"; CONTEXT_LIMIT = "context_limit"; RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"; AWAITING_INPUT = "awaiting_input"; COMPACTING = "compacting"

def normalize_terminal_text(text: str) -> str
    # strip ANSI escapes and \r; drop lines matching GIT_OUTPUT_LINE_PATTERNS
    # (git log/diff/commit lines: r"^(commit [0-9a-f]{7,}|Author:|Date:|diff --git|index [0-9a-f]+\.\.|@@ |[-+]{3} [ab]/)");
    # drop lines that are saved-transcript commands (cat|bat|less|more|tail|head ... transcript|output|hud|.txt);
    # lowercase is NOT applied here (callers use re.I).

def progress_digest(text: str) -> str
    # sha1 of normalize_terminal_text(text) with volatile UI lines removed:
    # spinner glyphs [⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏·✻✽✶✳✢], "esc to interrupt", elapsed counters r"\(\d+[smh]\b.*?\)",
    # r"\b\d+\s*tokens?\b", r"\b\d+[smh]\s+elapsed\b", "? for shortcuts", the idle prompt line, blank lines.

RATE_LIMIT_TEXT_PATTERNS: tuple[re.Pattern[str], ...]   # port of OMC tmux-detector RATE_LIMIT_PATTERNS +
    # OMC_HUD_RATE_LIMIT_SCREEN_PATTERNS: r"rate limit", r"usage limit", r"quota exceeded", r"too many requests",
    # r"try again later", r"limit reached", r"hit your limit", r"hit .+ limit", r"resets? .+ at", r"5[- ]?hour",
    # r"\bweekly\s+(?:usage\s+)?(?:limit|quota|cap|allowance|allocation)\b",
    # r"you(?:'|’)ve\s+(?:hit|reached)\s+(?:your\s+)?(?:session\s+|usage\s+)?limit", r"\blimit\s+resets?\b",
    # r"stop\s+and\s+wait\s+for\s+limit\s+to\s+reset", r"\b429\b(?!\d)(?=.*(?:rate|limit|request))" ,
    # r"rate_limit(?:ed|_error)?", r"too_many_requests", r"quota_(?:exceeded|limit|exhausted)"
    # NOTE: NO bare r"429" and NO bare r"overloaded" (false positives: 0.4291, step 4290, "GPU overloaded").
CONTEXT_LIMIT_PATTERNS   # OMC #213 tokens: context_limit, context_window, context_exceeded, context_full,
    # max_context, token_limit, max_tokens, conversation_too_long, input_too_long, plus TUI text:
    # r"context (?:window )?(?:is )?(?:full|low|exceeded)", r"prompt is too long", r"compact(?:ing)? (?:the )?conversation"
AUTH_ERROR_PATTERNS      # OMC #1308 — the 16 tokens verbatim (authentication_error … insufficient_scope) as
    # word-bounded matches; plus r"\bplease (?:run )?/login\b", r"\bnot logged in\b", r"\binvalid api key\b".
    # NOTE: '401'/'403' only when adjacent to auth vocabulary: r"\b40[13]\b(?=.*(?:unauthori[sz]ed|forbidden|auth))".
USER_ABORT_PATTERNS      # exact tokens aborted|abort|cancel (word-bounded) + substrings user_cancel, user_interrupt,
    # ctrl_c, manual_stop, "^\s*interrupted by user"; bare "interrupt" is deliberately EXCLUDED (OMC #2478).
AWAITING_INPUT_PATTERNS  # permission/question dialogs — never send Enter into these:
    # r"do you want to (?:proceed|allow|continue)", r"^\s*❯?\s*\d+\.\s", r"\[\d+\]", r"esc to cancel",
    # r"yes,? (?:and )?(?:don't|do not) ask again", r"allow (?:once|always)", r"press enter", r"enter to confirm",
    # r"select an option", r"choice:", r"waiting for (?:your )?(?:input|response|approval)", r"trust (?:this|the) (?:folder|workspace)"

def classify_never_block(text: str, *, is_interrupt: bool | None = None,
                         heartbeats: Sequence[HeartbeatRecord] = (), now: datetime | None = None,
                         compacting_window_sec: float = 300.0) -> NeverBlockReason | None
    # Precedence: is_interrupt → USER_ABORT; then over normalize_terminal_text(text) restricted to the LAST 60
    # non-empty lines: USER_ABORT > CONTEXT_LIMIT > RATE_LIMIT > AUTH_ERROR > AWAITING_INPUT;
    # then COMPACTING if any heartbeat has status COMPACTING with last_tick_at within compacting_window_sec of now.
    # Rationale (OMC persistent-mode bypass order): the platform's own stops win over "waiting for the user".

def parse_rate_limit_reset(text: str, *, now: datetime, tz: tzinfo | None = None) -> datetime | None
    # Recognize: "resets? (?:at )?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)" (today; if already past → tomorrow),
    # "reset(?:s)? in (\d+)\s*(min|minute|hour|second)s?", "try again in N (s|sec|min|minutes|hours)",
    # "retry[- ]after[: ]+(\d+)" (seconds), ISO-8601 timestamps. Local tz = `tz or now.tzinfo`. None if absent.

def compute_pause_until(now: datetime, reset_at: datetime | None, *, attempt: int, config: "WatchdogConfig") -> datetime
    # reset_at + 15 s jitter-free slack if given; else now + min(config.rate_limit_backoff_base_sec * 2**attempt,
    # config.rate_limit_backoff_max_sec).

def pane_ready_for_nudge(text: str) -> bool
    # OMC paneLooksReady AND NOT paneHasActiveTask AND no AWAITING_INPUT pattern in the last 40 lines:
    # ready := last non-empty line matches r"^\s*(?:[│┃║▌▐▏▕╎┆┊]\s*)?[›>❯]\s*" (idle prompt) or any such line
    #          exists in the last 5 non-empty lines; active := "esc to interrupt" | "background terminal running" |
    #          r"^[·✻]\s+[A-Za-z][A-Za-z0-9''-]*(?:\s+[A-Za-z][A-Za-z0-9''-]*){0,3}(?:…|\.{3})$" in last 40 lines.

class WatchdogConfig(BaseModel):
    enabled: bool = True
    stall_threshold_sec: int = 1200          # 20 min (specs/watchdog.md); tests induce 10-min stalls with a lower value
    startup_grace_sec: int = 120
    nudge_enabled: bool = True               # tmux only; Sam: default ON with the pane-ready guard
    nudge_delay_sec: int = 30                # dwell before first nudge and between nudges (OMC idle-nudge)
    nudge_budget: int = 3                    # per run (OMC maxCount)
    nudge_message: str = "Continue working on your assigned task and report concrete progress (not ACK-only)."
    resume_nudge_budget: int = 2             # after a rate-limit pause ends and nothing moves
    escalate_grace_sec: int = 120            # stall persists this long with nudges impossible/exhausted → escalate
    kill_headless_on_escalate: bool = True   # tmux never kills (human-facing); headless has no other lever
    rate_limit_backoff_base_sec: int = 60
    rate_limit_backoff_max_sec: int = 1800
    rate_limit_max_pause_sec: int = 6 * 3600
    hard_max_restarts: int = 3               # consumed by PR-B's driver; declared now so config is stable
    progress_paths: list[str] = []           # extra files/dirs whose mtime advance counts as progress
    model_config = ConfigDict(extra="forbid")

def resolve_watchdog_config(project: WatchdogConfig | None = None, *, env: Mapping[str, str] | None = None) -> WatchdogConfig
    # env kill switch: ZO_WATCHDOG=0 → enabled=False; ZO_WATCHDOG_STALL_SEC overrides stall_threshold_sec (tests/ops).

class WatchdogState(BaseModel):              # persisted at <memory_root>/heartbeats/_watchdog.json
    zo_session_id: str = ""
    started_at: datetime
    last_tick_at: datetime | None = None
    ticks: int = 0
    last_progress_at: datetime
    baseline_ticks: dict[str, int] = {}     # agent_key → tick_count seen at start (pre-existing files don't count)
    seen_ticks: dict[str, int] = {}
    last_digest: str | None = None
    last_file_mtimes: dict[str, float] = {}
    stall_since: datetime | None = None
    nudges_used: int = 0
    last_nudge_at: datetime | None = None
    resume_nudges_used: int = 0
    escalated_at: datetime | None = None
    stall_events: int = 0
    paused_at: datetime | None = None
    paused_until: datetime | None = None
    paused_reason: str | None = None
    pause_attempts: int = 0
    total_paused_sec: float = 0.0
    last_never_block: str | None = None

def new_state(*, now: datetime, zo_session_id: str = "", heartbeats: Sequence[HeartbeatRecord] = ()) -> WatchdogState
def load_state(memory_root: Path) -> WatchdogState | None      # fail-open
def save_state(memory_root: Path, state: WatchdogState) -> Path  # atomic

# Evidence observers — each returns True iff it observed NEW progress and updates state in place.
def observe_heartbeats(state: WatchdogState, heartbeats: Sequence[HeartbeatRecord]) -> bool   # any key whose tick_count > seen (and > baseline)
def observe_text(state: WatchdogState, text: str) -> bool                                        # progress_digest changed (first observation = False)
def observe_files(state: WatchdogState, paths: Sequence[Path]) -> bool                           # any mtime advanced / new file (dirs: newest entry mtime, one level)

class StallAction(StrEnum): NONE = "none"; NUDGE = "nudge"; RESUME_NUDGE = "resume_nudge"; PAUSE = "pause"; RESUME = "resume"; ESCALATE = "escalate"

class StallVerdict(BaseModel):
    action: StallAction
    stalled: bool
    reason: str                       # human sentence for comms/DECISION_LOG
    never_block: NeverBlockReason | None = None
    freshness: Freshness = Freshness.UNKNOWN
    process_dead: bool | None = None
    progress: bool = False
    evaluated_at: datetime

def evaluate(state: WatchdogState, config: WatchdogConfig, *, now: datetime, text: str,
             heartbeats: Sequence[HeartbeatRecord], progress: bool, process_dead: bool | None,
             is_interrupt: bool | None = None, can_nudge: bool) -> StallVerdict
```

`evaluate()` is the whole decision policy, pure and unit-testable. Contract:

1. If `progress`: `state.last_progress_at = now`; clear `stall_since`; if paused → this is a verified resume → `action=RESUME` (accumulate `total_paused_sec`, clear pause fields).
2. `reason = classify_never_block(text, is_interrupt=…, heartbeats=…, now=now)`; `state.last_never_block = reason`.
3. `reason == RATE_LIMIT`: if not paused → `action=PAUSE` (`paused_at=now`, `paused_until=compute_pause_until(...)`, `pause_attempts+=1`); if paused and `now >= paused_until` → extend (`pause_attempts+=1`, new `paused_until`), still `PAUSE`; if `now - paused_at > rate_limit_max_pause_sec` → `ESCALATE` with reason "rate-limit pause exceeded max". Return.
4. Paused and reason is None (banner gone) and no progress: if `now < paused_until` → `NONE`; if `now >= paused_until` and `can_nudge` and `resume_nudges_used < resume_nudge_budget` → `RESUME_NUDGE`; if `now >= paused_until` and cannot nudge (headless) → `NONE` until `paused_until + rate_limit_backoff_base_sec`, then `ESCALATE` if still nothing (headless RESUME requires progress). Return.
5. Any other never-block reason → `NONE` (never nudge; `stall_since` untouched but stall clock does not run: set `last_progress_at = now` for COMPACTING only — compaction is progress; for CONTEXT_LIMIT/AUTH_ERROR/USER_ABORT/AWAITING_INPUT leave the clock — they may become stalls but they are still never nudged; escalation is allowed for AUTH_ERROR/CONTEXT_LIMIT after `stall_threshold_sec` so a dead session doesn't hang forever, with `reason` naming the cause). Return.
6. Startup grace: `now - started_at < startup_grace_sec` → `NONE`.
7. `stalled = process_dead is True or (now - last_progress_at) >= stall_threshold_sec`. If not stalled → `NONE` (clear `stall_since`).
8. Stalled: set `stall_since` (first time: `stall_events += 1`). Decide:
   - `process_dead is True` → `ESCALATE`.
   - `can_nudge and nudges_used < nudge_budget and (last_nudge_at is None or now - last_nudge_at >= nudge_delay_sec) and (now - stall_since >= nudge_delay_sec or nudges_used > 0)` → `NUDGE`.
   - `nudges_used >= nudge_budget and now - last_nudge_at >= nudge_delay_sec` → `ESCALATE`.
   - `not can_nudge and now - stall_since >= escalate_grace_sec` → `ESCALATE`.
   - else `NONE` (waiting on dwell).
   - `ESCALATE` fires ONCE per stall (guard on `escalated_at` newer than `stall_since`); subsequent ticks return `NONE` with `stalled=True`.

Note: `evaluate()` mutates counters that are *decisions* (pause fields, `stall_since`, `escalated_at`, `stall_events`, `last_progress_at`); the CALLER increments `nudges_used`/`last_nudge_at`/`resume_nudges_used` only after the nudge was actually delivered.

Process identity (in `watchdog.py`, section "Process identity"; may delegate to a new `src/zo/_proc.py` if `watchdog.py` would exceed 500 lines — core builder decides; `surrogate.py` is NOT modified in PR-A):
```python
def pid_alive(pid: int) -> bool                     # os.kill(pid, 0); ESRCH → False; EPERM → True (alive, not ours)
def process_start_identity(pid: int, *, platform: str | None = None, run: Callable = subprocess.run) -> str | None
    # linux: /proc/<pid>/stat → field 22 after the last ')' → f"linux:{starttime}"; darwin: `ps -o lstart= -p PID`
    # under LC_ALL=C → f"darwin:{epoch_seconds}:0"; other: f"{platform}:{ps lstart raw}"; None on any failure.
def is_valid_process_start_identity(value: object, *, platform: str | None = None) -> bool   # OMC regex allowlist, ≤1024 chars
def identities_may_match(recorded: str, observed: str) -> bool     # equal, or darwin same-second with usec wildcard "0"
def is_process_dead(pid: int | None, recorded_identity: str | None, *, platform=None, run=subprocess.run) -> bool
    # POSITIVE PROOF ONLY: pid None → False; not alive (ESRCH) → True; alive and recorded identity valid and observed
    # identity valid and not may_match → True (recycled pid); anything unknown/EPERM → False.
```

Tests for core (`tests/unit/test_watchdog.py`, module docstring names WS-C + checks 11–12, section comments `# ---- <mechanism> (oracle check N) ----`, "seeded" in seeded-failure test names):
- taxonomy: parametrized positives per reason (≥3 each incl. the real Claude Code banner "You've hit your usage limit · resets at 3pm", "prompt is too long", "please run /login", "Do you want to proceed? ❯ 1. Yes"), negatives (`val_loss 0.4291`, `step 4290`, `GPU overloaded`, `commit 8466d29 fix weekly report`, `$ cat transcript.txt ... rate limit`), precedence (rate-limit banner + permission menu → RATE_LIMIT), `is_interrupt=True` → USER_ABORT, compacting heartbeat inside/outside window.
- `parse_rate_limit_reset`: "resets at 3pm" (today/tomorrow rollover), "resets at 14:30", "try again in 5 minutes", "retry-after: 90", none.
- freshness three-state; `evaluate()` scenario table with an injected clock: (a) **seeded 10-min stall** with `stall_threshold_sec=600`: ticks at t=0..11 min, no progress → `NUDGE` on the first tick past threshold+dwell, `NUDGE` ×3 spaced by `nudge_delay_sec`, then `ESCALATE` exactly once, then `NONE`; (b) **rate-limited is NOT nudged**: same clock but text carries the banner → `PAUSE` then `NONE`/`PAUSE`, never `NUDGE`; (c) **check 12 resume**: banner at t0 with "resets at" → `paused_until` parsed; at t≥paused_until banner gone, no progress → `RESUME_NUDGE`; then progress → `RESUME` with `total_paused_sec` accumulated; (d) headless (`can_nudge=False`) resume requires progress; (e) `process_dead=True` → `ESCALATE` immediately after grace; (f) startup grace suppresses; (g) `awaiting_input` never nudged; (h) compacting resets the clock; (i) progress via each observer (heartbeat tick delta ignoring baseline files, digest change ignoring spinner/counter churn, file mtime advance).
- identity: linux `/proc` parse (fixture string with a `)` inside comm), darwin `ps` mocked, malformed → None/not-dead, EPERM → alive, recycled pid → dead, unknown observed → not dead.
- persistence: `write_heartbeat`/`load_all_heartbeats` round-trip + atomicity (no partial file), `_watchdog.json` excluded, `sweep_stale_heartbeats`, `save_state`/`load_state` round-trip, `resolve_watchdog_config` env kill switch, `WatchdogConfig(extra="forbid")`.

---

## 2. Heartbeat writer — hooks + shim + wiring (builder: hooks)

- `.claude/settings.json`: append a SECOND entry to the existing `PostToolUse` array (keep the `Write|Edit` cascade-reminder entry untouched): matcher `"*"`, command `bash .claude/hooks/zo-hookkit.sh heartbeat 2>/dev/null || exit 0`, timeout 5. Do not add new events.
- `.claude/hooks/zo-hookkit.sh`: unchanged routing (`python3 -m zo.hookkit heartbeat`), but export `ZO_HOOK_EVENT_TS="$(date -u +%s)"` (cheap; not required by handler). Keep the `src/zo` guard.
- `src/zo/hookkit.py`:
  - Make the top-level `from zo.contracts import …` LAZY (inside the handlers that use it: subagent-stop, sealed-paths) so `heartbeat` costs no pydantic import. `_SEALED_DEFAULTS` gets the literal `"contracts.json"` and adds `"heartbeats"` (prefix match seals the whole subtree — verify with the existing `_sealed_prefixes` logic; agents' Write/Edit into `<memory_root>/heartbeats/…` must be denied — seeded test).
  - New `_agent_identity(data) -> tuple[str | None, str | None]` returning `(agent_type, agent_id)`; DO NOT change `_agent_name`.
  - New `_handle_heartbeat(data)`: stdlib-only (json/os/datetime), NO import of `zo.watchdog` (pydantic). Resolve `memory_root = _memory_root(_repo_root())`; None → return. `agent_key = agent_id or f"lead-{session_id}"`; path `<memory_root>/heartbeats/<agent_key>.json`; debounce: if file mtime < 2 s ago and event is PostToolUse → return; read existing `tick_count`; write JSON with EXACTLY the `HeartbeatRecord` fields (schema_version, agent_key, agent_id, agent_type, session_id, zo_session_id (env `ZO_SESSION_ID`), pid (env `ZO_LEAD_PID` if set else None), process_start_identity (env `ZO_LEAD_PID_IDENTITY` or None), last_tick_at ISO-8601 UTC with `+00:00`, status, last_event, tick_count+1) via tmp + `os.replace`. Status by `hook_event_name`: PostToolUse → `executing`; Stop → `ready`; SubagentStop → `shutdown`; PreCompact → `compacting`; SessionEnd → `shutdown`. `last_event` = `tool_name` for PostToolUse else `hook_event_name`.
  - Call `_handle_heartbeat(data)` (fail-open, wrapped in `contextlib.suppress(Exception)`) at the END of `_handle_drift_guard`, `_handle_subagent_stop`, `_handle_precompact`, `_handle_session_end` so those events also stamp — without changing their outputs.
  - `_handle_post_tool_failure`: add `is_interrupt`, `agent_id`, `agent_type` to the failure record (do not remove existing fields).
  - Register `"heartbeat": _handle_heartbeat` in `_HANDLERS`.
- `.gitignore`: add `memory/zo-platform/heartbeats/`, `memory/zo-platform/plan-ledger.json`, `memory/zo-platform/contracts.json` (verify with `git check-ignore -v`; note the `!memory/zo-platform/` re-include order — negations must come before these ignores or use paths after it).
- Tests: `tests/unit/test_hookkit.py` — heartbeat written keyed by `agent_id` (subagent payload) and by `lead-<session_id>` (no identity); JSON validates against `zo.watchdog.HeartbeatRecord` (import allowed IN TESTS); tick_count increments; debounce; status mapping per event; fail-open when memory root unresolvable (no file, exit 0); heartbeats **sealed**: seeded Write into `<memory_root>/heartbeats/x.json` → deny JSON (pattern of `test_ledger.py::…sealed…`); failure record carries `is_interrupt`. `tests/integration/test_hooks_shim.py` — extend `TestSettingsWiring` to assert the heartbeat PostToolUse entry; end-to-end `_run_shim("heartbeat", payload, env={ZO_MEMORY_ROOT: tmp})` writes the file; shim still exits 0 with malformed stdin.

---

## 3. Wrapper integration (builder: wrapper)

`src/zo/_wrapper_models.py`:
- `AgentStatus`: add `PAUSED_RATE_LIMIT = "paused_rate_limit"`, `STALLED = "stalled"`.
- `LeadProcess`: add `pid_start_identity: str | None = None`, `nudges_used: int = 0`, `stalled: bool = False`, `paused_until: datetime | None = None`, `resume_at: datetime | None = None`, `pause_total_sec: float = 0.0`.

`src/zo/wrapper.py` (keep < 500 lines… it is 1043 today; the file-size rule is already broken — do not make it worse: put the tick logic in a new `src/zo/_wrapper_watchdog.py` mixin/helper module (`WatchdogRunner` class holding config, state, memory_root, comms, clock, evidence paths) and keep wrapper.py changes to wiring + the pause loop + `_paste_and_submit` + pid capture):
- `LifecycleWrapper.__init__`: add `self._proc: subprocess.Popen | None = None` and `self._wd: WatchdogRunner | None = None`.
- `wait_for_completion(..., watchdog: WatchdogConfig | None = None, memory_root: Path | None = None, zo_session_id: str = "", delivery_repo already exists)`: build `self._wd = WatchdogRunner(...)` when `watchdog and watchdog.enabled and memory_root`; runner `start(now)` snapshots baseline heartbeats (`new_state`), sweeps stale files, seeds `progress_paths` = [`memory_root/plan-ledger.json`, comms log dir (`self._comms` log dir if exposed), `delivery_repo/.zo/experiments` if it exists] + config.progress_paths. Tear down in the existing `finally` (persist state).
- **tmux loop `_wait_tmux`**: hoist ONE `pane_text = self._capture_tmux_pane(pane_id, lines=200)` per iteration (before the liveness reads) and reuse it for `on_status` (5-line snapshot = last 5 lines of it). Call `self._watchdog_tick(process, text=pane_text, can_nudge=True)` right after `_maybe_open_training_pane()` and BEFORE the liveness reads, so it also runs on the suspected-dead `continue` path. Timeout check: use `elapsed = time.monotonic() - start_time - self._wd.paused_seconds()` when a runner exists.
- **headless loop `_wait_headless`**: replace the retry loop with: `new_text = self._read_new_output(process)` (byte cursor over BOTH stdout_log and stderr_log; keep a rolling window of the last 16 KB as `self._wd_text_window`); call `self._watchdog_tick(process, text=window, can_nudge=False)` after `_check_gate_mode_change()` and before the `rc` check; if `rc is not None` and the runner's last never-block is RATE_LIMIT (or the final window matches) → status `RATE_LIMITED`, `resume_at` = parsed reset (may be None) — no retries in the wrapper (PR-B's driver relaunches). Delete `_backoff_wait`/`_max_retries` retry semantics from the loop (keep `_detect_rate_limit` for the exit-classification path only, tightened to the watchdog patterns — remove bare `429`/`overloaded`).
- `_watchdog_tick(process, *, text, can_nudge)`: delegate to `self._wd.tick(process=process, text=text, can_nudge=can_nudge, now=self._wd.clock())` which returns the `StallVerdict`; the WRAPPER performs side effects by action:
  - `NUDGE`/`RESUME_NUDGE`: guard `pane_ready_for_nudge(text)`; if ready → `self._paste_and_submit(pane_id, config.nudge_message)` then runner `record_nudge(now, resume=...)`; comms `log_checkpoint(agent="watchdog", phase="lifecycle", subtask="nudge", progress=f"nudge {n}/{budget}: {reason}")`; if NOT ready → comms checkpoint `subtask="nudge-skipped"` (pane busy/awaiting input) — no keys sent.
  - `PAUSE` (first entry only, i.e. `paused_at == now`): `process.status = PAUSED_RATE_LIMIT`, `process.paused_until = …`; comms checkpoint `subtask="rate-limit-pause"` with the reset time.
  - `RESUME`: `process.status = RUNNING`, `pause_total_sec` updated; comms checkpoint `subtask="rate-limit-resume"` (verified=True/False).
  - `ESCALATE`: comms `log_error(agent="watchdog", error_type="stall", severity="blocking", description=verdict.reason, escalated_to="human")`; `process.stalled = True`; if headless and `config.kill_headless_on_escalate` → `self.kill_session(process)`; the loop returns with `status=STALLED`. tmux: keep waiting; when the session eventually ends, final status = `STALLED` if `process.stalled` and no progress since escalation, else the normal completion status.
  - First stall detection (`stall_since` set this tick): comms `log_error(agent="watchdog", error_type="stall", severity="warning", ...)` once per stall.
  - Persist runner state every tick (fail-open) and write a one-line JSONL trace per tick to `<memory_root>/heartbeats/_watchdog-ticks.jsonl` (`ts, action, stalled, reason, never_block, progress`) — check-11's seeded test asserts on this line.
- `_paste_and_submit(pane_id, text)`: extracted from the launch path; uses a NAMED buffer (`tmux load-buffer -b zo-nudge -` from stdin, `tmux paste-buffer -b zo-nudge -d -t pane`, sleep 1, `send-keys -t pane Enter`); refactor `_launch_tmux` to call it (behaviour-preserving; the existing `_verify_prompt_submitted` retry stays).
- tmux PID + identity (best-effort): after pane creation capture `#{pane_pid}` (shell pid), then during/after `_wait_for_tui_ready` resolve the claude child via `pgrep -P <shell_pid>` (first hit) — store `pid` and `pid_start_identity = process_start_identity(pid)` on `LeadProcess`; None if not resolvable (unknown ≠ dead). Headless: set `pid_start_identity` next to `pid=proc.pid`. Export `ZO_LEAD_PID`/`ZO_LEAD_PID_IDENTITY` is NOT required (hooks run inside the lead; skip).
- Existing tests: rewrite `test_detects_rate_limit_and_backs_off` and `test_rate_limit_exhausts_retries` to the new semantics (running process + rate-limit text → PAUSED, no sleep-backoff; exited process + rate-limit text → RATE_LIMITED with `resume_at`).
- New tests in `tests/unit/test_wrapper.py` (follow the class-patch pattern for `_tmux_pane_alive/_tmux_claude_running/_capture_tmux_pane/_kill_tmux_window`, `mock.patch("zo.wrapper.time.sleep")`, scripted `side_effect` lists, injected clock via `WatchdogRunner(clock=...)`):
  - **`test_seeded_10min_stall_detected_and_escalated_within_one_poll` (check 11)** — tmux loop, `stall_threshold_sec=600`, `nudge_delay_sec=0`, heartbeat files aged, pane text neutral+idle prompt: assert `_paste_and_submit` called ≤ `nudge_budget`, an `error_type="stall"` comms line, `_watchdog-ticks.jsonl` shows `escalate` on the first tick after budget exhaustion, and the loop's final `LeadProcess.status == STALLED` when the pane dies afterwards.
  - **`test_seeded_rate_limited_session_is_never_nudged` (check 11)** — pane text carries the Claude usage-limit banner: `_paste_and_submit` never called; `process.status == PAUSED_RATE_LIMIT` observed via `on_status`/state; comms `rate-limit-pause` line.
  - **`test_seeded_rate_limit_pause_auto_resumes_on_reset` (check 12)** — banner with "resets at HH:MM", injected clock advances past it, banner disappears, no progress → one `RESUME_NUDGE` (paste called once with the nudge message), then heartbeat delta → `rate-limit-resume` checkpoint, `status == RUNNING`, `pause_total_sec > 0`, timeout accounting excludes the pause.
  - Same three on the headless harness (`can_nudge=False`: no paste ever; running+banner → PAUSED; exited+banner → RATE_LIMITED with `resume_at`; stall → `kill_session` called once → STALLED).
  - `test_watchdog_tick_runs_on_suspected_dead_path`, `test_single_pane_capture_per_poll`, `test_wrapper_proc_defaults_none`, `test_permission_dialog_is_never_nudged`, `test_paste_and_submit_uses_named_buffer`, `test_watchdog_disabled_when_config_off_or_no_memory_root` (no runner, loops behave exactly as before).

---

## 4. Config + CLI threading + docs (builder: config-cli-docs)

- `src/zo/project_config.py`: `ProjectConfig` gains `watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)` (import from `zo.watchdog`); `save_project_config` must round-trip it (nested dict). Add `model_config = ConfigDict(extra="ignore")` explicitly with a comment (documented choice, not accidental) — do NOT forbid, legacy configs may carry unknown keys.
- `src/zo/cli.py`: `ProjectContext.make_project_config()` returning `ProjectConfig | None` (None for legacy layouts); in `build` resolve `wd_cfg = resolve_watchdog_config(pcfg.watchdog if pcfg else None)`; add `extra_env["ZO_SESSION_ID"] = <comms session id>`; `_launch_and_monitor(..., watchdog: WatchdogConfig | None = None, memory_root: Path | None = None, zo_session_id: str = "")` → `wrapper.wait_for_completion(..., watchdog=..., memory_root=..., zo_session_id=...)`; after the wait: handle `AgentStatus.STALLED` (red "Session stalled — watchdog escalated; see logs/comms") and `RATE_LIMITED` with `resume_at` ("rate-limited; resets at …; rerun `zo continue` after") BEFORE the generic else. Add `--no-watchdog` flag to `build`/`continue` mapping to `enabled=False` (single concern per flag, PR-038). `_print_status` needs no change (checkpoint/error already render) — verify.
- `tests/unit/test_project_config.py`: watchdog block round-trip through save/load; legacy config without the block → defaults; unknown key ignored. `tests/unit/test_cli.py`: `--no-watchdog` plumbing → `wait_for_completion` receives `enabled=False`; default path passes `memory_root` and a config; `STALLED` status prints the stalled message (patch `wait_for_completion`).
- Docs: `specs/watchdog.md` — Status → implemented (PR-A), §3.1 cron tick → wrapper poll-loop external checker (plan supersedes), §3.4 remediation = taxonomy → nudge (bounded, tmux, pane-ready guard) → escalate (log; headless kill); reroute/respawn deferred to the PR-B driver; §3.5 config keys = `WatchdogConfig` fields; §4 integration points = real files/functions; §5 acceptance = checks 11–12 test names; §6 rewritten. `docs/reference/v2-rearchitecture.mdx`: watchdog feature row/status text (Phase 3 in progress: watchdog shipped, fresh-context loop next). Do NOT bump README test badge or counts (integrator does after the final count).

---

## 5. Definition of done (integrator verifies)
- `python3 -m pytest -q` green (baseline 929 + new), `ruff check src/` clean, `bash scripts/validate-docs.sh` 0 failures.
- Every mechanism has (a) a seeded-failure test and (b) a wiring test proving it is invoked from the runtime path (settings.json entry asserted; `_watchdog_tick` asserted from both loops; CLI passes config to the wrapper).
- No new event types in comms; no writes outside `<memory_root>/heartbeats/`; heartbeats sealed; `.gitignore` verified with `git check-ignore`.
- MIT attribution comment present in `watchdog.py` for the ported pattern tables and identity logic.
