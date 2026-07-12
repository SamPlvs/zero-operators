<!--
Provenance: approved implementation plan from session 040 (2026-07-12).
Persisted here per PR-046 (internal ~/.claude/plans files are ephemeral;
the peaceful-valley roadmap plan from session 028 was lost that way).
Status at persistence time: approved by Sam; PR D1 mockups generated but
NOT yet reviewed/verified/committed (branch claude/vscode-design-mockups).
-->

# ZO Feature Roadmap — Four Workstreams, Sequenced

## Context

Sam wants a sequenced roadmap for the next generation of ZO features, implemented as separate PR series:

1. **Lit review mode** — strengthen the in-project Phase 0 literature review and make it opt-in for all workflow modes (user chose this over a standalone command).
2. **Cross-phase handoff** — the `RETURN_TO_PHASE` backedge primitive (F3 Phase A; design of record in DECISION_LOG session-028), addressing prior external feedback.
3. **Slack integration** (WhatsApp later, behind a transport abstraction) — bidirectional: notifications when away from desk + relay instructions/gate decisions into the live lead session.
4. **VS Code UI** — stop requiring raw tmux; **design mockups first** (ZO brand system) for approval, then build per the session-028 architecture (headless tmux engine + xterm.js renderer).

**Caveman integration was dropped from scope by Sam** ("No need for caveman now") — remove nothing, build nothing; it stays a roadmap card.

Recommended implementation order: **WS4-PR1 (mockups, cheap, needs Sam's approval) → WS1 (lit review) → WS2 (backedge) → WS3 (Slack bridge) → WS4 (VS Code engine + extension)**. The mockup PR is design-only and unblocks nothing else, so it goes first to give Sam something to react to while code work proceeds.

## Verified key facts (from exploration)

- **Latent bug (confirmed by direct read)**: `AGENT_PHASE_MAP` ([_orchestrator_phases.py:21-40](src/zo/_orchestrator_phases.py)) gives `research-scout`/`code-reviewer` phases 1–6 only, but `data-engineer` includes `phase_0`. Since `decompose_plan()` overwrites `assigned_agents` via `_agents_for_phase()` (orchestrator.py:333-336, 809-845), today's runtime phase_0 roster is `[data-engineer]` — the hard-coded `["code-reviewer","research-scout"]` at `_orchestrator_phases.py:264` is dead code. Phase 0 also has **no `required_artifacts`** — its automated gate verifies nothing.
- `GateDecision` = {PROCEED, HOLD, ITERATE, ESCALATE} ([_orchestrator_models.py:39-45](src/zo/_orchestrator_models.py)); no RETURN_TO_PHASE yet. `advance_phase()` has **no production caller** — the lead session mutates STATE.md; Python re-reads it at next launch. Backedge enforcement must hook the paths that actually run: CLI launch (between decompose and get_current_phase) AND advance_phase.
- Text injection into a running lead session exists only inline (wrapper.py:253-270 load-buffer→paste-buffer→send-keys, duplicated at :386-398) — must be extracted; shared by bridge inbound + VS Code gate approval.
- Session discovery: per-PID lock files `<delivery>/.zo/surrogates/locks/<pid>.json` (surrogate.py:240-321) — but the pane id isn't in them yet (cli.py writes the lock before the pane id is known).
- Outbound substrate: `logs/comms/{date}.jsonl` (event types message|decision|gate|error|checkpoint, comms.py:31-38) — exactly PRD §8's sanctioned "integration bridge tails the JSONL" pattern. Bridge must dedup on byte offset (`_print_status`'s `event_id` dedup at cli.py:885-888 keys on a field no event has — latent no-op; fix in passing).
- No `tmux new-session -d` / `pipe-pane` support exists; wrapper's tmux path requires being inside tmux (`_is_in_tmux`, wrapper.py:973-976). The roadmap's "zero wrapper.py changes" claim was optimistic — the engine is an additive detached-launch branch.
- `_extract_extra_sections` (`_memory_formats.py:98-121`) preserves unknown STATE.md sections verbatim → any new structured section (`## Revisits`) must be excluded there or it duplicates on every save.
- An existing detailed design for grounded literature retrieval lives at `~/.claude/plans/well-if-its-open-zany-frost-agent-a339b548df8b14ce1.md` (`src/zo/scholar.py`: Semantic Scholar + arXiv + Papers-with-Code, provenance-verified SOTA numbers, optional `httpx` extra) — planned as a follow-up PR to WS1, not bundled.

---

## WS1 — Lit review: strengthened, opt-in Phase 0 (1 PR, ~2–3 days; scholar follow-up ~4–5 days)

### Design
- **Opt-in mechanism**: new optional plan section `## Literature Review` (aliases "literature review", "prior art") following the `## Experiment Loop` parser precedent (plan.py `_OPTIONAL_SECTION_ALIASES` :568-579, `_parse_experiment_loop` :668-691). New `LiteratureReviewSpec` pydantic model: `enabled`, `min_approaches` (default 3), `min_baselines` (default 2), `focus` (free text). Semantics: classical_ml/deep_learning get phase_0 iff section present and `enabled` ≠ false; **research mode keeps phase_0 always-on** (`enabled: false` → validation warning, ignored).
- **One enriched factory**: new `literature_review_phase(spec)` + `with_phase_0(phases, spec)` in `_orchestrator_phases.py`; `research_phases()` rewritten to use it (deletes the under-specified block at :259-267). Six subtasks (prior-art survey, SOTA summary, baseline definition, OSS catalog, experiment plan + oracle thresholds, references). Composition happens in `Orchestrator._resolve_phases()` (:303-319, the PR #99 seam) so subclass overrides keep working.
- **Enforced gate artifacts** (existence-checked by `_check_artifacts`; gate ITERATEs naming missing files): `research/literature_review.md`, `research/baseline_definition.md`, `research/experiment_plan.md`, `research/references.bib`. Deliberately NOT required: `sota_summary.md`, `open_source.md` (PRIORS PR-004: customer domains may have no published benchmarks — don't block), `pretrained_models.yaml` (meaningless for most classical_ml). Artifact names standardize on the research-scout contract; `specs/workflow.md:60-92` updated to drop the stale `prior_art_survey.md` naming.
- **AGENT_PHASE_MAP fix**: add `phase_0` to `research-scout`; **remove** `phase_0` from `data-engineer` (accidental current state — flag as behavior change in DECISION_LOG); do NOT add code-reviewer (no code in phase_0). Low-token exception in `_agents_for_phase` (:836-837): keep research-scout in phase_0 only (if the user opted in, silently dropping the phase's only agent defeats the opt-in) — document in `docs/reference/low-token-preset.mdx`.
- **New prompt builder** `_prompt_research_context(phase)` (modeled on `_prompt_experiment_context` :1192-1268; wired into `build_lead_prompt` :397-427): the four gate-required paths + optional ones, quality bars (≥`min_approaches` cited approaches, ≥`min_baselines` baselines, eval protocol consistent with prior art), the plan's oracle metric/threshold injected so the scout validates or challenges it, PR-004's "no benchmark ≠ blocker" escape hatch, `spec.focus`, Gate 0 review framing.

### Files
`src/zo/plan.py` (spec + parsing + validation warning), `src/zo/_orchestrator_phases.py` (factory + map fix), `src/zo/orchestrator.py` (`_resolve_phases` composition, `_literature_review_enabled`, `_prompt_research_context`, low-token exception), `.claude/agents/research-scout.md` (+`baseline_definition.md` ownership, gate-artifact checklist).

### Docs cascade
`specs/workflow.md` (Phase 0 section retitle + artifact reconciliation), `specs/plan.md` (new optional section), `specs/agents.md` §7, `docs/concepts/phases-and-gates.mdx`, `docs/concepts/the-plan.mdx`, `docs/reference/low-token-preset.mdx`, README phase table if present.

### Tests
Unit: factory composition (prepend, `phase_1.depends_on == ["phase_0"]`), opt-in parsing (present/absent/`enabled: false`/aliases/int coercion/research-mode warning), decompose regressions (classical without section → 6 phases; with → 7 phases and `assigned_agents == ["research-scout"]`), low-token phase_0 exception, **negative artifact-gate tests per PRIORS PR-035 — omit each required artifact individually → ITERATE naming it**, `get_current_phase` ordering, STATE.md `phase_0:` round-trip, mid-project opt-in determinism, prompt content. Integration: full decompose → gate-ITERATE-without-artifacts → write files → PROCEED → phase_1 current; session round-trip. Python 3.11 + 3.12.

### Follow-up PR (optional, Sam decides when reached): `zo.scholar`
Per the existing design doc: `src/zo/scholar.py` (PwC + Semantic Scholar + arXiv, pydantic models, `python -m zo.scholar` JSON CLI, `.zo/scholar-cache/`, `ZO_SCHOLAR_OFFLINE=1`, optional `scholar = ["httpx>=0.27"]` extra mirroring the fastembed pattern), recorded-fixture tests incl. phantom-SOTA rejection, research-scout contract updated to require provenance-backed numbers. WS1's gate list deliberately doesn't depend on scholar output, so this composes cleanly later.

---

## WS2 — Cross-phase backedge: RETURN_TO_PHASE (2 PRs, ~5–7 days)

### Design (follows DECISION_LOG session-028, one justified deviation)
- **State machine — deviation from the session-028 sketch (log it in DECISION_LOG)**: on applying a revisit of phase M requested by phase N: M `COMPLETED → ACTIVE` (+ clear subtasks, `_abort_running_experiments` if phase_4); **N → `PENDING` with M appended to `depends_on`** (NOT BLOCKED — BLOCKED means "human escalation required" per PR-037 and the `get_current_phase` contract; PENDING-with-deps-met already resumes N automatically the moment M re-completes, with zero changes to resolution order, no new PhaseStatus, no consumer blast radius); intermediate COMPLETED phases between M and N → PENDING with cleared subtasks (their outputs are stale by construction).
- **Request channel**: structured file `<delivery>/.zo/revisit_request.json` (`from_phase`, `to_phase`, `reason`, `constraint`, `requested_by`, `requested_at`) written by the lead (works in full-auto; writing one JSON file is far more reliable than hand-editing STATE.md — PR-036 family). Consumed with central validation at BOTH points Python actually runs: top of `advance_phase()` and in `cli.build` between `decompose_plan()` and `get_current_phase()` (steps 7→8). On consumption: validate → apply or reject → archive to `.zo/revisits/handled-<ts>.json` (idempotent). `GateDecision.RETURN_TO_PHASE` added as the evaluation outcome + an explicit `apply_human_decision(..., target_phase=)` branch for the human-driven path.
- **Guardrails (convergence/token blow-up was Sam's flagged risk)**: global budget `--max-cross-phase-revisits` default **2** per project (persisted counter — survives sessions); duplicate-reason rejection via Jaccard ≥0.9 against previously applied records for the same edge (refactor `experiment_loop`'s `_tokenize`/`_jaccard` into a shared public `text_similarity()`; parity-pin test); structural validation (to_phase must precede from_phase, be COMPLETED; no self/forward edges); budget-exhausted/dead-end → ESCALATE + `_record_learning()` evolution prior, never silent; the remaining budget is shown in the lead prompt (itself a convergence guardrail); full audit to comms + DECISION_LOG + a phase snapshot on M's re-activation.
- **New module** `src/zo/_orchestrator_revisit.py` (~250 lines; orchestrator.py is already 1,666 lines): `RevisitRequest`/`RevisitRecord`/`RevisitPolicy` models, `read_pending_request` (loud ValueError on malformed JSON), `validate_request`, `archive_request`.
- **Persistence**: `SessionState` gains `revisit_count: int = 0` + `revisit_records: list[dict]` (defaults → old STATE.md parses unchanged); new `## Revisits` section in STATE.md (emitted only when records exist; pipe-delimited lines; parse-time validation with `_VALID_REVISIT_STATUSES` frozenset + drift-guard test, per PR-036). **Trap**: `_extract_extra_sections` (`_memory_formats.py:98-121`) must skip `## Revisits` like `## Phases` or it duplicates on every save. `_restore_phase_states` re-applies open records' added `depends_on` (factory resets them otherwise) and resolves records whose to_phase is COMPLETED.
- **Prompts**: `_prompt_revisit_reason(phase)` (injected when phase is a reopened to_phase: from-phase, reason, constraint, "address the constraint specifically; don't redo unrelated work"; plus a resumed-from_phase variant) and `_prompt_revisit_howto()` (teaches the JSON protocol, legitimate triggers, remaining budget; omitted in supervised mode). Both modeled on `_prompt_experiment_context`/`_render_loop_briefing`.
- **CLI/commands**: `--max-cross-phase-revisits INT` on build/continue (same plumbing as `--max-iterations`); `zo gates return-to-phase --to phase_2 --reason ... [--constraint ...]` (thin writer, `requested_by="human"`); new slash command `.claude/commands/gates/return-to-phase.md` (instructs writing the JSON, NOT hand-editing STATE.md). **validate-docs Check 3 counts command files — bump command counts in README/docs/COMMANDS.md in the same PR.**
- **Ordering rule**: a revisit request found at a phase_4 gate is processed BEFORE `_auto_iterate_if_needed` (else the loop mints a child experiment against stale upstream artifacts) — dedicated test.

### PR split
- **PR B1 — core primitive** (~3–4 days): revisit module, enum member, state machine in `advance_phase`/`apply_human_decision`, `text_similarity` refactor, persistence + round-trip tests, unit tests. Inert without a writer — safe merge.
- **PR B2 — channel + surface** (~2–3 days): CLI-launch consumption wiring, flag, `zo gates return-to-phase`, slash command, prompt builders, integration tests (full flow incl. session-boundary resume + budget exhaustion), doc cascade (`specs/workflow.md` new section + Gate-3 text update, `phases-and-gates.mdx` gate decisions, `specs/memory.md` `## Revisits` schema, build/continue docs, roadmap.mdx item → shipped, command counts).

---

## WS3 — Slack bridge (3 PRs, ~4–6 days; WhatsApp later behind the same Protocol)

### Design
- **Process model**: standalone **`zo bridge`** sidecar (long-running CLI), not a thread in `_launch_and_monitor` — survives across runs, answers "nothing running", zero risk to the TTY-fragile orchestration core, and matches PRD §8's sanctioned watcher pattern. Registers in the liveness registry with `role="bridge"`; **`_peers_live` consumers (cli.py:758-796) must filter by role** so a running bridge never suppresses overlay cleanup or consolidation (subtlest change — explicit tests).
- **Pane discovery**: enrich the surrogate lock file with `tmux_pane_id`, `team_name`, `project`, `zo_root` via new `surrogate.update_session()`, called from `_launch_and_monitor` right after `launch_lead_session` returns (~cli.py:808). Old locks lack the field → bridge replies "session found but pane unknown (older run)".
- **Transport**: `Transport` Protocol (`send(Notification)`, message iteration, `close()`); implementations `ConsoleTransport` (always available; used by tests + `--transport console`) and `SlackTransport` via official **slack-sdk Socket Mode** (no public endpoint needed; bidirectional; hand-rolling the protocol has no upside). Packaging: optional extra `bridge = ["slack-sdk>=3.27"]` with the fastembed-style guarded import. `WhatsAppTransport` (Meta Cloud API/Twilio) later.
- **Outbound templates** (documented in `specs/comms.md` per PRD §8): gate reached/result (metric vs threshold, tier, pass/fail + "reply `approve` or `reject <reason>`" hint when mode is supervised/auto); errors — immediate only for severity blocking|critical, rest folds into digest; checkpoint digest batched (default 10 min, never per-checkpoint); session start/end (from lock lifecycle + wrapper completion checkpoint); on-demand status reply.
- **Inbound grammar** (first token): `status` (works with nothing running — live_sessions + STATE.md summary + last events), `approve` / `reject <reason>` (inject `/gates:approve` / `/gates:reject <reason>` into the orchestrator-role pane — the slash commands already perform the full STATE.md/DECISION_LOG/comms mutation; a parallel gate_decision file would duplicate that logic), `mode supervised|auto|full-auto` (`memory.write_gate_mode` — the already-remote hot-reloaded path, works without a session), free text → relayed into the pane prefixed `[remote instruction from human via slack]:`. Multiple live sessions → filter `role == "model"`, newest wins, ambiguity noted in reply; report-role surrogates never targeted.
- **Security**: hard allowlist `allowed_user_ids` in config; **empty allowlist = inbound disabled** (outbound-only); unauthorized senders get a terse denial + a warning-severity comms ErrorEvent for audit; every injection logged as a MessageEvent (`agent="bridge"`, recipient lead). Config at `~/.zo/bridge.yaml` (outside the public repo, chmod-600 check) + env overrides (`ZO_SLACK_APP_TOKEN`/`ZO_SLACK_BOT_TOKEN`) + optional `bridge:` block in `<delivery>/.zo/local.yaml` (gitignored; `LocalConfig` gains an optional field). Tokens never tracked, never echoed. Optional `confirm_free_text: true` echo-and-confirm mode.
- **Reliability**: byte-offset tailing with daily-rotation handling (drain old file to EOF, then switch); offsets persisted to `logs/bridge/state-{project}.json` (inside gitignored `logs/`); restart resumes from offset, corruption → seek to newest EOF + one "skipped history" notice (no replay spam); Slack auto-reconnect + capped backoff on sends; single-threaded poll loop + Slack client thread feeding a `queue.Queue` (no asyncio — matches codebase style). Events carry `project` — tailer filters on it so two projects' bridges don't cross-notify. Drive-by: fix the `_print_status` dedup no-op (key on file+line, not `event_id`).

### New modules (each <500 lines)
- `src/zo/tmux_io.py` — **shared foundation, also used by WS4**: `send_text_to_pane(pane_id, text, *, submit, verify)` (+retry via capture-pane), `load_file_to_pane`, `capture_pane`, `pane_alive` — logic lifted from wrapper.py:253-270/364-398; wrapper refactored to call it (net negative lines).
- `src/zo/_bridge_models.py` — `BridgeConfig`/`Notification`/`InboundMessage`/`TailState` + config loader.
- `src/zo/bridge_transports.py` — Protocol + Console + Slack transports.
- `src/zo/bridge.py` — `CommsTailer`, template renderers, `InstructionRouter`, `BridgeService.run()`.

### CLI
`zo bridge -p <project> [--repo] [--transport slack|console] [--dry-run] [--outbound-only]` (`--dry-run` renders the last ~20 events through templates and exits — template debugging without Slack).

### Tests
Unit: tailer (offset resume, rotation, restart-after-truncation, malformed lines), templates (all five event types, severity filtering, digest batching, approve-hint only in supervised/auto), router (allowlist deny+audit, grammar, target selection, provenance prefix, confirm handshake), config (env overrides, missing token, precedence, chmod warning), tmux_io (subprocess monkeypatched; retry parity with old wrapper logic), SlackTransport with `sys.modules`-mocked slack_sdk + skip-if-not-installed guard. Integration: real CommsLogger → FakeTransport notifications; inbound `approve` → asserted `/gates:approve` injection with pane id from enriched lock; `mode auto` → gate_mode file change; zero locks → "nothing running"; wrapper regression suite green after tmux_io extraction. All green on 3.11/3.12 **without slack-sdk installed**.

### PR split
- **PR C1** (~0.5–1 day): `tmux_io.py` extraction + wrapper refactor; lock enrichment + `update_session` + cli wiring; role-aware peer filtering; `_print_status` dedup fix; tests. **Shared foundation for WS4.**
- **PR C2** (~2–3 days): bridge core (models/config/tailer/templates/router/ConsoleTransport), `zo bridge` (console + dry-run), unit + integration tests, specs/comms.md section.
- **PR C3** (~1–2 days): SlackTransport + optional extra + reconnect/backoff + mocked tests + docs (`docs/cli/bridge.mdx` + mint.json nav, COMMANDS.md, README "Built on" slack-sdk entry, roadmap.mdx).
- **PR C4 (later, unscoped)**: WhatsAppTransport behind the same Protocol.

---

## WS4 — VS Code extension, design-first (7 PRs, ~3.5–4.5 weeks total)

### Repo placement (recommendation, adjusts the DECISION_LOG note)
Monorepo top-level **`vscode/`** directory in zero-operators, with a documented extraction path to a `zo-vscode` repo once `session.json` `schema_version: 1` freezes and the extension ships to the marketplace. Rationale: the runtime contract WILL churn during development — two repos means two-PR version-skew dances for a single developer; `vsce` publishes fine from a subdirectory; validate-docs/ruff/pytest scopes untouched; CI adds a path-filtered Node job.

### Stage 1 — PR D1: HTML design mockups (FIRST deliverable; Sam's approval gates all Stage-2 work) (~2–3 days)
`design/vscode/` — 10 static browser-viewable files following the existing `design/*.html` convention, sharing `tokens.css` (ZO brand vars + `[data-theme="light"]` overrides + VS Code chrome-simulation vars). Each page has a dark/light toggle. Files:
- `tokens.css`, `00-overview.html` (index + v1-vs-deferred annotations)
- `01-workbench.html` — hero composite: full VS Code window (activity bar with the simplified-C mark, ZO sidebar, lead terminal as editor area, comms feed bottom panel, status bar)
- `02-sidebar.html` — tree in 4 states (no `.zo/` detected / idle / running with agent status badges + gates + training nodes / ended-reattach)
- `03-terminal-panel.html` — lead xterm.js frame, sub-agent tabs + 2×2 grid toggle, composer input, reconnect + pane-died states
- `04-comms-feed.html` — timeline with distinct treatments for the 5 event types, filters, auto-scroll pin
- `05-gate-approval.html` — inline gate card (metric vs threshold, tier, breakdown, Approve/Reject…/Iterate), reject-reason popover, gate-mode segmented control, attention toast
- `06-training-dashboard.html` — hand-rolled SVG loss curve (coral-soft area fill), stat tiles, epoch progress/ETA, checkpoint list, experiment picker
- `07-start-run.html` — plan picker, gate-mode, lead model, low-token, max-iterations, bypass-permissions (with warning copy), live `zo build … --headless-tmux` command preview, preflight panel
- `08-status-and-palette.html` — status bar items, command palette entries, notification toasts

Webview constraints baked in so approval ≈ buildable: no runtime external fonts (bundle Geist/JetBrains Mono/Instrument Serif woff2 — all SIL OFL; fallback stacks); strict CSP (no CDN, nonce'd single script per page); ZO tokens with documented `--vscode-*` fallbacks ("brand" vs "inherit editor theme" setting); sidebar designed at 300px (min 170), panels fluid from 400px. Exit criterion: Sam reviews `00-overview.html`, approves/edits each screen, sign-off recorded in DECISION_LOG.

### Stage 2 — implementation
- **PR D2 — Python engine** (~3–4 days): new `src/zo/runtime.py` (builds on WS3's `tmux_io.py`): `init_runtime` (creates `<delivery>/.zo/runtime/` + `panes/`), `attach_pipe` (capture-pane backfill then `tmux pipe-pane -o`), `sync_panes` (poll `list-panes -s`, attach pipes to new panes — this is how sub-agent panes stream: Claude Code teammate-mode creates panes inside the detached session since TMUX is set there), atomic `write_manifest`, `resize`. **Runtime contract** (`schema_version: 1`, documented in new `docs/reference/runtime-contract.mdx`): `.zo/runtime/session.json` (project, team, tmux_session, size, heartbeat, wrapper_pid, status, absolute paths {comms_dir, memory_root, gate_mode_file, experiments_dir} — solves "comms lives in zo_root, not delivery repo", and `panes: [{pane_id, role, title, log, status}]`) + `panes/p<N>.log` raw ANSI streams. Wrapper changes (additive): `launch_lead_session(headless_tmux=False)` new branch BEFORE the `_is_in_tmux` check; `_launch_tmux(detached=True)` swaps `new-window` for `tmux new-session -d -s zo-{team}-{ts} -x 220 -y 50`; `_wait_tmux` gains a guarded no-op `_maybe_sync_runtime` hook; `_maybe_open_training_pane` needs no change (its `_is_in_tmux` guard correctly skips). CLI: `--headless-tmux` on build/continue (mutually exclusive with `--no-tmux`); new `zo runtime` group (`send --pane … --text … --submit`, `list --json`, `kill`) — **all tmux logic stays in Python** where it's tested (PR-001/PR-022/PR-031 spirit); the extension never shells to tmux directly. Existing wrapper tests must pass unmodified — that's the regression gate. Early spike: verify ANSI/dimension coupling with a real Claude TUI before polishing.
- **PR D3 — extension scaffold** (~3 days): `vscode/` TypeScript project (esbuild; contributes viewsContainer + zoSessions TreeView + zoComms WebviewView; commands zo.startRun/attach/stop/approveGate/rejectGate/setGateMode/openTerminals/openTraining; activation `workspaceContains:.zo/**`); services: manifest reader + heartbeat staleness, per-file byte-offset logTailer, comms JSONL tailer with daily rollover, `zoCli` child_process wrapper; sessions tree, status bar; CI node job.
- **PR D4 — terminals** (~3–4 days): xterm.js webview per pane (created at manifest cols/rows — ANSI is dimension-relative), tabs/grid, FileSystemWatcher → offset-read → `postMessage` → `term.write()` pipeline, composer (send lines/slash commands via `zo runtime send`), debounced resize → `zo runtime resize`, reattach-on-reopen (tmux survives VS Code restarts; heartbeat-fresh → offer reattach). **Input model v1 is deliberate**: read-only streams + composer; full per-keystroke TTY passthrough deferred (reintroduces the TTY risk class the architecture avoids).
- **PR D5 — comms feed + gate UX** (~2–3 days): feed timeline, gate approval card (one click = `zo runtime send --pane <lead> --text "/gates:approve" --submit`; reject prompts for reason), gate-mode control (`zo gates set`), notifications.
- **PR D6 — training dashboard + start-run form** (~3 days): SVG charts hand-rolled from `.zo/experiments/<id>/metrics.jsonl` + `training_status.json` via `experiments.resolve_active_experiment_dir`; start-run form invoking `zo build <plan> --headless-tmux …`.
- **PR D7 — polish** (~2–3 days): theme mapping/light mode, bundled fonts, `vsce` packaging + marketplace CI on `vscode-v*` tags, manual e2e script (`zo build <mnist plan> --headless-tmux` → session.json appears → logs grow → open VS Code → reattach checklist), docs (`docs/concepts/vscode-extension.mdx`, README).

### Known risks
ANSI dimension coupling (mitigated: fixed creation size, size in manifest, resize routed through Python; spike early); sub-agent pane discovery latency (2s sub-poll; tmux hooks are a later optimization); pane.log growth from TUI redraws (truncate per session, rotate later if needed); comms midnight rollover (unit-tested).

---

## Sequencing summary

| # | PR | Workstream | Effort |
|---|----|-----------|--------|
| 1 | D1 mockups (`design/vscode/`) — Sam approval gate for Stage 2 | WS4 | 2–3 d |
| 2 | A1 Phase 0 strengthening (+ AGENT_PHASE_MAP fix) | WS1 | 2–3 d |
| 3 | B1 backedge core primitive | WS2 | 3–4 d |
| 4 | B2 backedge channel + surface | WS2 | 2–3 d |
| 5 | C1 tmux_io + lock enrichment (shared foundation) | WS3 | 0.5–1 d |
| 6 | C2 bridge core + console transport | WS3 | 2–3 d |
| 7 | C3 Slack transport + docs | WS3 | 1–2 d |
| 8 | D2 headless-tmux engine + runtime contract | WS4 | 3–4 d |
| 9 | D3–D7 extension (scaffold → terminals → gates → training → polish) | WS4 | ~3 wks |
| — | A2 `zo.scholar` grounding layer (optional follow-up) | WS1 | 4–5 d |
| — | C4 WhatsApp transport (later) | WS3 | unscoped |

Every PR follows the repo's automatic protocols: STATE.md/DECISION_LOG/PRIORS updates before commit, doc cascade + `scripts/validate-docs.sh`, full CI mirror (ruff `src/`, pytest on 3.11 AND 3.12, validate-docs) per PRIORS PR-039, conventional commits, no AI attribution, no client identifiers.

## Verification (per workstream)

- **WS1**: unit + integration suites above; end-to-end sanity: a classical_ml fixture plan with `## Literature Review` decomposes to 7 phases and the phase_0 gate ITERATEs until the four artifacts exist (drive via the integration test, not a paid run).
- **WS2**: integration test runs the full backedge flow incl. a session-boundary resume and budget exhaustion; manually drive one real `zo build` on the MNIST demo plan with a hand-written `.zo/revisit_request.json` to watch the amber notice + STATE.md `## Revisits` appear.
- **WS3**: `zo bridge --transport console --dry-run` against a real project's comms logs renders templates; integration test proves approve→injection with mocked tmux; live smoke: run `zo build` (MNIST), have the bridge post gate events to a private Slack channel, reply `status` and `approve`, confirm the lead session receives `/gates:approve`. Suites green without slack-sdk installed.
- **WS4**: D1 = browser review of the 10 mockups (Sam sign-off). D2 = existing wrapper tests unmodified + new runtime tests + a real `zo build --headless-tmux` smoke asserting session.json + growing pane logs + `tmux has-session`. D3–D7 = mocha unit + `@vscode/test-electron` integration + the manual e2e checklist (kill VS Code mid-run → reopen → reattach).
