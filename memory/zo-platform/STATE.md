# STATE.md — Zero Operators Platform Build

project: zero-operators-build
mode: maintain
phase: complete
iteration: 1
status: complete

## Current Position

ZO **v1.0.2** + **`--low-token` mode** (session-024) — cost-saving preset for users on Anthropic Pro plans / student accounts / anyone watching their daily message budget. New CLI flag `--low-token` + plan YAML field `low_token: true` activate a profile that swaps the lead orchestrator from Opus to Sonnet (~5× cheaper), caps Phase-4 `max_iterations` at 2 (down from 10), drops `stop_on_tier` to `could_pass`, filters `research-scout` from cross-cutting agents, disables the Haiku headline ticker (~60 calls/hr), defaults gate mode to `full-auto`, and sets `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60` in the Claude Code subprocess env. Compose with override flags (`--lead-model {opus,sonnet,haiku}`, `--max-iterations N`, `--no-headlines`) — precedence is CLI > plan > preset > base default. Banner shows `[low-token]` badge for visual confirmation. Estimated savings: ~70-80% (MNIST-equivalent run drops from ~$11 to ~$2-3). **Architecture stays CLI-launcher-based** — no SDK refactor; prompt caching, Batch API, Files API explicitly out of scope (would require switching from `claude` CLI subprocess to direct Anthropic SDK; deferred). Implementation: `_LOW_TOKEN_PRESET` constant in `cli.py:255` (single source of truth), `LoopPolicy.low_token` + `_LOW_TOKEN_LOOP_CLAMPS` in `experiment_loop.py`, `Orchestrator.__init__(low_token=...)` threaded through `_agents_for_phase` (filters research-scout) and `build_lead_prompt` (drops dedicated adaptations section + compacts roster), `LifecycleWrapper.launch_lead_session(extra_env=...)` for env var propagation (tmux: prefixed to command string; headless: `subprocess.Popen(env=...)`). New page `docs/concepts/low-token-mode.mdx` covers preset table, trade-offs, when-not-to-use. README gains "Built on" acknowledgements section listing Claude Code + 11 deps with licenses, plus "Optional integrations (planned)" section documenting ccusage / Repomix / caveman as future work. **Tests:** +29 new (704 total + 7 skipped) — `TestResolvePolicyLowToken` (5 cases, plan-overrides-clamp + CLI-override-wins precedence), `TestAgentsForPhaseLowToken` (3 cases, research-scout filtering + custom-agent name-collision safety), `TestLowTokenOrchestrator` (4 cases, prompt section trimming), `TestLowTokenFlags` (8 cases, click flag plumbing + banner badge + preset constant shape), `TestLowTokenPropagation` integration (5 cases, end-to-end propagation CLI → Orchestrator → LoopPolicy + plan frontmatter round-trip), `TestFrontmatter` low_token/lead_model parsing (3 cases). ruff clean on `src/zo/`, validate-docs 10/10 (1 pre-existing test-count warning unrelated). Session-023 still closes the three small open issues from STATE.md's Known Issues list: (1) confirmed the **Plan.md Environment section** was already shipped (session-013) — parser handles it via `_OPTIONAL_SECTION_ALIASES['environment']`, plan template at `cli.py:2856` populates it from `detect_environment()`, round-trip is covered by `tests/unit/test_plan.py:192/219`. The Known Issue entry was stale; removed. (2) Implemented **platform-aware Docker scaffold** — `scaffold.py` previously hardcoded `deploy.resources.reservations.devices: capabilities: [gpu]` in every `docker-compose.yml`, which fails on macOS (Docker Desktop has no GPU passthrough) and is a no-op on Linux without an NVIDIA GPU. New `_COMPOSE_GPU_TEMPLATE` + `_COMPOSE_CPU_TEMPLATE` (CPU variant uses `pytorch:2.4.0-cpu` base image and a header comment explaining when it applies). `scaffold_delivery()` gains `gpu_enabled: bool | None = None` parameter — `None` probes via `detect_environment().gpu_count > 0`, falls back to GPU template on probe failure (safest default for Linux build servers). CLI's `_init_commit_writes` detects host GPU at scaffold time and passes through. Service name kept as `gpu` across both templates so README quickstart is platform-independent. (3) **MNIST Phase 6 packaging** flagged as out-of-scope code work — it requires running ZO end-to-end against the MNIST plan (a Claude session, ~$11 in tokens), not a code change. Deferred for user decision. **Tests:** 6 new `TestPlatformAwareCompose` tests in `tests/unit/test_scaffold.py` covering GPU/CPU explicit modes, auto-detect both ways, detection-failure fallback, and CPU service-name parity. One existing test (`test_cli.py::TestScaffoldDelivery::test_scaffold_creates_compose`) updated to pass `gpu_enabled=True` explicitly so it's host-independent. Test count 669 → 675 (+6). ruff clean on `src/zo/`, validate-docs 10/10 (1 pre-existing test-count warning unrelated). Session-022 still ships brand polish: (1) `website/public/favicon.svg` was still the old orbital mark — replaced with the new simplified C in single coral so it reads on both light and dark browser tabs; (2) hero image was visually undersized at desktop — flipped `.hero-inner` columns from `1.1fr 1fr` (copy-weighted) to `1fr 1.15fr` (image-weighted), only affects >900px viewports so mobile stacking unchanged; (3) section 02 idea-diagram side labels (`decompose / verify / ship`) were positioned at the level of source/destination boxes instead of the action gaps between them — moved each into the gap so they label the transition (DECOMPOSE between plan.md→chips, VERIFY between chips→oracle, SHIP between oracle→trained-model); (4) oracle box `must · should · could` text (147px wide) overflowed its 120-wide rect by 14px on each side — widened to 170 (still centered at x=240 via translate 155), 11px symmetric padding. Also fixed 2px arrow misalignment for `analysis` and `package` chips. **README banner regenerated (v6 final) and consolidated into `design/banner/`** — new sub-dir holds master `readme-banner.svg` (typography + mark + frame overlay) + final composites at 1280×640 + 2560×1280 retina + source `workshop.png` photo + `render.mjs` Canvas-sandbox compositing script + a README explaining the asset structure and edit workflow. Old top-level `design/readme-banner.{svg,png}` removed. Root README image path updated `design/readme-banner.png` → `design/banner/readme-banner.png`. Session-021 still ships the full visual identity refresh: new palette (canvas `#12110F`, paper `#F4EFE6`, coral `#D87A57`, dusk + moss for status), new typography (Geist sans + Cormorant Garamond italic + JetBrains Mono — replacing Share Tech Mono / Rajdhani), new mark (simplified C — circle + diagonal slash + centered coral dot — replacing the orbital). Public website rewritten as Astro 5 static (single `src/pages/index.html` + `public/` assets, mobile-tested) with light/dark theme toggle, persisted in localStorage. Old multi-component Astro site (12 .astro components, 4 JSON data files, 2 scripts) deleted. design/ replaced with new brand-system.html (dark + light) + logos.html + font-pairings.html + shared styles.css + logos.js. README banner swapped to `design/readme-banner.png`. CLAUDE.md Design System rewritten. Cascade docs updated (frontend-engineer.md, documentation-agent.md). Version bumped 1.0.1 → 1.0.2 across pyproject.toml + __init__.py + cli.py. validate-docs 10/10 (1 pre-existing test-count warning). Cloudflare Pages compatible — same astro.config.mjs, same `npm run build → dist/`.

## Completed

- [x] Phase 0: Agent definitions (17 files), settings.json, build plan v2.0
- [x] Phase 1: Plan Parser, Target Parser, Comms Logger, setup.sh
- [x] Phase 2: Memory Layer, Semantic Index
- [x] Phase 3: Orchestration Engine + Lifecycle Wrapper + gate mode toggle
- [x] Phase 4: Evolution Engine, CLI, integration tests
- [x] Phase 5: End-to-end validation (MNIST: 99% accuracy, 98 tests, ~$11)
- [x] Slash commands: 24 commands across 8 categories
- [x] Documentation: COMMANDS.md reference, interactive HTML demo
- [x] README: full user workflow, architecture, commands, e2e results
- [x] v1.0.1: Interactive tmux agent sessions (send-keys + paste-buffer)
- [x] v1.0.1: ZO brand panel at startup (project, mode, phase, gate info)
- [x] v1.0.1: Smart build (auto-detects fresh/continue/plan-edited)
- [x] v1.0.1: Pre-launch phase review in all modes
- [x] v1.0.1: zo maintain removed (zo build handles plan edits)
- [x] v1.0.1: zo continue is thin alias for zo build
- [x] v1.0.1: zo draft accepts multiple file/dir paths + interactive refinement
- [x] v1.0.1: Live monitoring dashboard (tasks, team, comms events)
- [x] v1.0.1: Doc-code consistency: validate-docs.sh (10 checks, <2s)
- [x] v1.0.1: Hook system: SessionStart, PreToolUse, PostToolUse, Stop
- [x] v1.0.1: Self-evolution: PR-005 (enforcement > aspiration), three-layer defense
- [x] v1.0.1: Full doc audit: agent counts 16→17, version 1.0.0→1.0.1
- [x] v1.0.2-pre: Phase persistence fix (SessionState tracks per-phase status + completed subtasks)
- [x] v1.0.2-pre: Blocking gates fix (get_current_phase returns GATED phases for human review)
- [x] v1.0.2-pre: Phase artifact contracts (required_artifacts on all 6 phases)
- [x] v1.0.2-pre: Auto-generated Jupyter notebooks per phase (notebooks.py)
- [x] v1.0.2-pre: Delivery repo scaffold with Docker (scaffold.py, Dockerfile, docker-compose.yml)
- [x] v1.0.2-pre: zo preflight command (10 validation checks, GPU/Docker detection)
- [x] v1.0.2-pre: Delivery repo structure redesign (configs/, src/ by responsibility, experiments context trail, tests unit/ml split, docker/ subdir, STRUCTURE.md)
- [x] v1.0.2-pre: Orchestrator pipeline wiring (artifact validation at gates, auto-notebook generation, Docker/STRUCTURE.md in lead prompt)
- [x] v1.0.2-pre: setup.sh auto-fix — interactive prompt installs uv, Claude CLI, global settings (bash 3.2 compatible)
- [x] v1.0.2-pre: Claude CLI install updated to official curl method (replaced deprecated npm install)
- [x] v1.0.2-pre: setup.sh verifies zo CLI callable on PATH (check #11), auto-fixes via symlink to ~/.local/bin/
- [x] v1.0.2-pre: setup.sh deps check upgraded from dry-run to actual `uv sync`
- [x] v1.0.2-pre: zo draft works without source docs — conversational, description-based, or interactive prompt
- [x] v1.0.2-pre: Draft plans write to main repo (not worktrees) via _main_repo_root()
- [x] v1.0.2-pre: Draft session wrap-up — Claude asks "anything else?" then tells user to /exit and run zo build
- [x] v1.0.2-pre: Brand banner (_show_banner) on all 6 CLI commands (build, draft, init, status, preflight, continue)
- [x] v1.0.2-pre: Phase 1 enriched — 13 subtasks (was 7), 5 agents (was 2) for production data workflows
- [x] v1.0.2-pre: Cross-cutting agents — code-reviewer + research-scout default on ALL phases, all workflow modes
- [x] v1.0.2-pre: README updated — zo draft docs reflect conversational flow + new usage patterns
- [x] v1.0.2-pre: Autonomous path handoff — zo init writes absolute delivery path to target file, auto-scaffolds delivery repo
- [x] v1.0.2-pre: init → draft → build pipeline carries context via target file (no user path passing)
- [x] v1.0.2-pre: Haiku headline summaries — live 1-line status every 60s during zo build
- [x] v1.0.2-pre: tmux orphan prevention — draft kills existing window before creating new one
- [x] v1.0.2-pre: Draft tests fixed — all use --no-tmux (was spawning real tmux windows)
- [x] v1.0.2-pre: zo gates set — toggle gate mode mid-session (supervised/auto/full-auto)
- [x] v1.0.2-pre: Full doc audit — COMMANDS.md, workflow.md, README, SAMPLE_PROJECT updated for consistency
- [x] v1.0.2-pre: Training metrics protocol (ZOTrainingCallback) — JSONL + status JSON for live dashboards
- [x] v1.0.2-pre: zo watch-training — Rich Live dashboard (progress bar, metrics table, sparkline, checkpoints)
- [x] v1.0.2-pre: Auto split-pane — wrapper detects training_status.json, splits tmux pane for dashboard
- [x] v1.0.2-pre: Model-builder contract updated with required ZOTrainingCallback usage
- [x] v1.0.2-pre: Phase 4 notebook reads from metrics.jsonl (with legacy fallback)
- [x] v1.0.2-pre: Auto test reports at gates — pytest JUnit XML → structured markdown test_report.md
- [x] v1.0.2-pre: Phase 1 report template (10 sections: schema, completeness, distributions, outliers, class, temporal, correlations, drift, splits, recommendations)
- [x] v1.0.2-pre: Phase 5 report template (7 sections: explainability, error analysis, bias, ablation, significance, reproducibility, verdict)
- [x] v1.0.2-pre: Agent contracts reference specs/report_templates.md for structured reports
- [x] v1.0.2-pre: Draft scout team — Plan Architect (Opus lead) + Data Scout (Sonnet) + Research Scout
- [x] v1.0.2-pre: zo draft CLI redesigned — --docs, --data, -d flags (all optional, conversational fallback)
- [x] v1.0.2-pre: _launch_and_monitor refactored — shared by build and draft, model/max_turns params
- [x] v1.0.2-pre: Agent count 17 → 19 (plan-architect, data-scout added)
- [x] v1.0.2-pre: Dynamic agent creation — .claude/agents/custom/ for project-specific specialists
- [x] v1.0.2-pre: Plan parser supports **Custom agents:** block (name: Model — role)
- [x] v1.0.2-pre: Orchestrator auto-creates custom agent .md files from plan at build start
- [x] v1.0.2-pre: Custom agents available for all phases (not restricted by AGENT_PHASE_MAP)
- [x] v1.0.2-pre: _prompt_roster scans both core and custom/ directories, labels each
- [x] v1.0.2-pre: Conversational `zo init` — Init Architect (Opus, 20th agent) interviews user, inspects target repo, routes writes through `zo init --no-tmux`
- [x] v1.0.2-pre: src/zo/environment.py — host detection (platform, Python, GPU count/names/memory, CUDA, NVIDIA driver, Docker, docker compose) with safe fallbacks
- [x] v1.0.2-pre: Plan template `## Environment` section auto-populated from detection (host + training target + data layout + Docker mounts)
- [x] v1.0.2-pre: Target template — `{target_branch}` placeholder + responsibility-based agent_working_dirs (src/data/, src/model/, src/engineering/, ...)
- [x] v1.0.2-pre: `zo init` headless flags — --no-tmux, --branch, --existing-repo, --base-image, --gpu-host, --data-path, --no-detect, --layout-mode
- [x] v1.0.2-pre: Scaffold `layout_mode={standard,adaptive}` — adaptive only adds ZO meta-dirs (configs/, experiments/, docker/, notebooks/phase/, reports/), preserves existing src/ + data/ layout
- [x] v1.0.2-pre: Scaffold .gitkeep only in truly empty dirs — no pollution of existing code dirs in overlay
- [x] v1.0.2-pre: `zo init` guardrails — --existing-repo must be a git dir, --layout-mode=adaptive requires --existing-repo, mutually-exclusive flag detection, branch existence warning, tmux availability check
- [x] v1.0.2-pre: `zo init --dry-run` — preview file tree, target/plan content, scaffold plan without writing (Init Architect runs this before every commit)
- [x] v1.0.2-pre: `zo init --reset` — deletes memory/{project}/, targets/{project}.target.md, plans/{project}.md; refuses without --yes unless user types project name; NEVER touches delivery repo
- [x] v1.0.2-pre: Init Architect partial-match + semantic-alias guidance — default to standard for partial src/ dirs (idempotent fill-in), adaptive + map for semantic aliases (src/data_loading → src/data)
- [x] v1.0.2-pre: Per-project agent adaptations — `**Agent adaptations:**` block in plan.md; Plan Architect populates during draft based on scout findings; orchestrator injects into spawn prompts at build time; works for both core (xai-agent, domain-evaluator) and custom agents; appended not replaced (agent `.md` files stay reusable)
- [x] v1.0.2-pre: Branded `zo --help` — `ZoGroup`/`ZoCommand` override `get_help()` to render a Rich-formatted banner (orbital mark ◎ + `ZERO OPERATORS` + version in brand amber) with sectioned headers (USAGE, QUICK START, COMMANDS, OPTIONS) and an init→draft→preflight→build→continue quick-start sequence; propagates to every subcommand and nested group automatically via `command_class`/`group_class`
- [x] v1.0.2-pre: Tmux TUI paste timing fix — increased wait from 3s to 8s, Enter delay from 0.5s to 1s; fixes blank-session bug where zo init/draft/build launched Claude but never submitted the prompt on cold starts
- [x] v1.0.2-pre: Agent session auto-cleanup — `_tmux_claude_running()` detects Claude exit via `pane_current_command`, `_kill_tmux_window()` closes leftover shell, `_generate_session_summary()` prints Haiku bullet summary before returning control to terminal
- [x] v1.0.2-pre: Preflight integration tests (9 tests) — fixture plan validation, parenthetical oracle fields, error formatting, full pipeline. Fixed 3 stacked bugs: `report.is_valid`→`.valid`, `i.field`→`.section`, oracle alias lookup strips parenthetical suffixes. Test count 476→485.
- [x] v1.0.2-pre: Lead prompt includes explicit "read full plan.md" instruction + autonomy level section based on gate mode
- [x] v1.0.2-pre: Denylist-first DL data-pipeline guidance codified (specs/workflow.md Subtask 1.3 callout + data-engineer.md Pipeline Principles section). Cross-reference to PR-026.
- [x] v1.0.2-pre: Domain-evaluator refactored to generic shell — domain identity comes exclusively from plan's `**Agent adaptations:**` block at build time. Agent file is reusable across projects; stop-rule prevents generic reports when adaptation missing.
- [x] v1.0.2-pre: Phase completion snapshots (C1) — `src/zo/snapshots.py`, `PhaseSnapshot` pydantic model with `schema_version`, MD+YAML frontmatter format, orchestrator hooks at both automated+human gate PROCEED paths, uses `memory_root` (auto-portable with `.zo/` layout). 23 unit + 5 integration tests. Test count 529 → 557.
- [x] v1.0.2-pre: Experiment capture layer (Phase 4) — `src/zo/experiments.py` (models + registry I/O + mint + MD parsers), `.zo/experiments/` in delivery repo, orchestrator mints one exp per Phase 4 iteration with `parent_id` lineage, `result.md` gate requirement, orchestrator parses Oracle's result → computes `delta_vs_parent`, aborts running exps on ITERATE (child gets mounted next prompt), `ZOTrainingCallback.for_experiment()` factory writes into exp dir, agent contracts updated (model-builder hypothesis+next, oracle-qa result, xai/domain-eval diagnosis), `zo experiments list/show/diff` CLI group. 38 unit + 10 orchestrator-flow + 9 CLI tests. Test count 557 → 617.
- [x] v1.0.2-pre: Autonomous experiment loop (Phase 4) — `src/zo/experiment_loop.py` (`LoopPolicy`, `LoopVerdict`, `evaluate_loop_state`, `check_dead_end`, `resolve_policy`). Orchestrator auto-iterates phase_4 in non-supervised modes: after Oracle's `result.md` is parsed and the experiment marked complete, the evaluator decides TARGET_HIT / BUDGET_EXHAUSTED / PLATEAU / DEAD_END / CONTINUE. CONTINUE → phase stays ACTIVE, subtasks cleared, next prompt mints child with `parent_id`, Model Builder auto-drafts `hypothesis.md` from parent's shortfalls (no human prompt). DEAD_END fires when last N hypotheses all Jaccard-similar ≥ threshold to an earlier exp (Model Builder stuck rephrasing). Plan can override defaults via optional `## Experiment Loop` block. Lead prompt + model-builder contract updated with auto-proposer protocol. 44 unit + 7 integration tests. Test count 617 → 669.
- [x] v1.0.2: Brand redesign v2 + website v2 — new palette (canvas/paper/coral/dusk/moss, oklch-based) + new typography (Geist + Cormorant Garamond + JetBrains Mono) + new mark (simplified C, no orbital). Old `design/` wiped (8 HTML + 3 SVG); new `design/` = `brand-system.html` (dark) + `brand-system-light.html` + `logos.html` + `font-pairings.html` + shared `styles.css` + `logos.js` + `readme-banner.{svg,png}` + `logo-dark.svg` (extracted from new mark). Old multi-component Astro website (12 `.astro` + 4 JSON + 2 scripts + `PLAN.md`) replaced with single-page Astro static (`src/pages/index.html` + `public/{styles.css, app.js, favicon.svg, robots.txt, sitemap.xml, assets/hero-workshop.png}`); mobile-tested with `@media` queries at 1024/900/640/400px + `@media (hover: none) and (pointer: coarse)`. Light/dark theme toggle (localStorage persistence). README banner + logo refs updated. CLAUDE.md Design System rewritten. frontend-engineer.md + documentation-agent.md path/palette refs updated. Cloudflare Pages compatible — verified `cd website && npm install && npm run build` produces correct `dist/`. Version cascade 1.0.1 → 1.0.2 across pyproject.toml + `__init__.py` + cli.py. PR #51 merged.
- [x] v1.0.2: Troubleshooting docs — `docs/TROUBLESHOOTING.md` covering sub-agent spawn crashes (macOS `kern.maxprocperuid=2666` + Claude Code 2.1.119 fixes + headless `--no-tmux` diagnostic), `zo: command not found` (PR-012 symlink workaround), tmux paste timing on cold start (PR-022/PR-031), build appearing stuck (no tmux session), worktree confusion (PR-013), bash 3.2 silent failures (PR-010), and where to look in logs. README links from Slash Commands section; Status section refreshed (v1.0.1 → v1.0.2, 17 → 20 agents, 476 → 669 tests, "pre-F5" row replaced with "1.0.2" row).
- [x] v1.0.2-post: `--low-token` mode — CLI flag + plan YAML field activate cost-saving preset (Sonnet lead, max_iterations=2, stop_on_tier=could_pass, drop research-scout cross-cutting, disable Haiku headlines, default gate-mode=full-auto, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60). Override flags `--lead-model`, `--max-iterations`, `--no-headlines` compose. Precedence CLI > plan > preset > base. Banner badge. README "Built on" acknowledgements section. +29 tests (704 total).
- [x] v1.0.2-post: Low-token docs expansion — `docs/concepts/low-token-mode.mdx` extended with FAQ (9 questions), worked-example sections (MNIST + tiny plan), side-by-side comparison table, when-to-use card group; `docs/concepts/the-plan.mdx` Frontmatter step documents `low_token` + `lead_model` fields with example; `docs/cli/overview.mdx` adds cost-saving flags table; `docs/quickstart.mdx` Step 5 Note callout for low-token; `docs/introduction.mdx` Tip callout; new `docs/reference/low-token-preset.mdx` (one-page preset card with knob reference + override flags + precedence table + visual confirmation example); new `docs/reference/cost-benchmark.mdx` (methodology + caveats + reproducing instructions + measurements table-stub); `docs/mint.json` adds new "Reference" navigation group; `docs/README.md` content-structure tree updated.
- [x] v1.0.2-post: Benchmark harness — `scripts/benchmark_low_token.sh` (executable, bash 3.2-compatible, ccusage-aware with manual JSONL fallback) for measuring default vs low-token MNIST cost end-to-end. Documents the manual tmux launch step (since `--no-tmux` is single-shot only and multi-phase orchestration needs interactive). Output: timestamped JSON files + summary. Script linted with `bash -n` clean.
- [x] v1.0.2-post: 15-test smoke suite verifying every low-token code path: imports, preset shape, lead model precedence, gate mode precedence, LoopPolicy clamps, plan frontmatter round-trip + backwards-compat, research-scout filtering, banner badge on/off, wrapper extra_env signature, click flag wiring (build + continue help), flag composition, frontmatter pydantic round-trip, env var value.
- [x] v1.0.2-post: docs/concepts/the-team.mdx frontmatter title fix — was `"Agents"` (legacy from before the page rename `concepts/agents` → `concepts/the-team` in commit a5a0592), now `"The team"` matching the file path and the link text used everywhere else (introduction.mdx Card, mint.json nav). Resolves the user-reported 404 cognitive issue where the sidebar showed "Agents" while link text said "The team" — the page was always at `/concepts/the-team`, but on stale Mintlify deploys the old `/concepts/agents` slug could 404. Title/path/link now all align.
- [x] v1.0.2-post: README test-count badge stale-fix — was `tests-675_passing`, updated to `tests-704_passing` matching the actual `pytest -q` output post-low-token-mode tests. validate-docs Check 6 still issues a benign warning because it counts grep-matched test FUNCTIONS (692) which is less than runtime-expanded tests (704) due to pytest parameterization — pre-existing measurement-method discrepancy noted previously, not a content issue.

## Known Issues

1. ~~Phase state not persisted between zo build calls~~ (RESOLVED: session-010)
2. ~~Blocking gates cause repeated sessions in auto mode~~ (RESOLVED: session-010)
3. ~~MNIST Phase 6 (packaging: model card, validation report) not completed~~ (RESOLVED: session-023, full MNIST demo re-run in `mnist-digit-classifier-delivery/` with all 6 phases of deliverables — 99.66% test accuracy, 16/16 tests pass)
4. ~~Agent permissions need broader .claude/settings.json allow patterns~~ (resolved)
5. ~~Device detection (Linux vs Mac) not yet implemented — affects Docker GPU passthrough~~ (RESOLVED: session-023, platform-aware scaffold)
6. ~~Plan.md missing Environment section for base_image, CUDA version, paths~~ (RESOLVED: session-013, verified in session-023)

## What's Next

1. ~~Portable project memory~~ (SHIPPED: PR #44-47, session-018)
2. **prod-001 Phase 2** — baseline models on GPU server. Phase 1 data pipeline complete (denylist approach, 297 tests, full doc QA). Re-alignment with full tag set (~15k tags) needed on GPU. UNBLOCKED by portable memory.
3. ~~Phase completion snapshots (C1)~~ (SHIPPED: session-019, snapshots.py + orchestrator hooks + 28 tests)
4. ~~Domain evaluator refactor~~ (SHIPPED: session-019, generic shell + plan adaptations)
5. Remote-data manifest support for `zo draft` (Data Scout reads YAML manifest when data is on a GPU server it can't introspect) — NEXT
6. ~~ZO learning: denylist-first data pipelines~~ (SHIPPED: session-019, codified in workflow.md + data-engineer.md)
7. ~~Experiment capture layer~~ (SHIPPED: session-019, capture only — the autonomous loop stays deferred per PR-005 until prod-001 Phase 4 generates real iteration data).
8. **Remote-data manifest for `zo draft`** — cancelled. Portable `.zo/` memory (PR #44) already solves the cross-machine case; run `zo draft` on whichever machine has the data.
9. ~~Autonomous experiment loop~~ (SHIPPED: session-020, full loop — plateau + budget + target + dead-end + auto-proposer, policy configurable via plan `## Experiment Loop`, supervised mode opts out).

## Deferred — Post prod-001 First Pass

7. **Experiment Tracker & Autonomous Iteration** — build AFTER prod-001 first pass generates real iteration data. Discussed in session 012. Scope:
   - Experiment registry (`experiments/registry.json`) — structured lineage: what was tried, why, what was learned, parent experiment
   - Hypothesis tracking — formal "hypothesis → config → result → conclusion" loop, prevents revisiting dead-ends
   - Cross-experiment analysis — auto-generated insights (which hyperparams matter, which architectures work for this data)
   - Plan refinement from results — if experiments reveal wrong assumptions, feed back to update plan/Phase 2 outputs
   - Budget-aware experiment selection — given N iterations left, pick most informative next experiment
   - Design from real prod-001 failure patterns, not speculation (PR-005 principle: enforcement from experience)

## Session Metadata

last_checkpoint: 2026-04-26T22:00:00Z
last_session: session-024 (in-progress — PR #57 merged; doc-fix follow-up: redirect rule for legacy /concepts/agents slug, escaped MDX prose dollar signs, partial bench attempt)
branch: main (post PR #57 merge)
v1_status: COMPLETE — all 8 PRD §9 acceptance criteria met, all Known Issues closed
docs_site: scaffolded under docs/ with Mintlify (mint.json + 16 pages: 3 get-started + 7 concepts + 4 cli + 2 reference; redirect rule /concepts/agents → /concepts/the-team for stale-cache hardening); awaiting connection at docs.zero-operators.dev
test_count: 704 passed, 7 skipped (ZO platform); 16 passed (mnist demo); 19 passed (cifar10 demo); 297 passed (prod-001)
benchmark: scripts/benchmark_low_token.sh harness in place; first measured attempt 2026-04-26 aborted at ~17min/$13.59 — lead idle on sub-agent permission gate; surfaced architectural finding that Claude Code 2.1.92 spawns TeamCreate sub-agents on `claude-opus-4-6` regardless of agent .md frontmatter `model:` field (so low-token's lead-model swap saves on lead-side spend only; sub-agents stay on Opus). Revised savings estimate downward 70-80% → 50-65%. Details in docs/reference/cost-benchmark.mdx "Findings from the partial run".
demo_results:
  mnist-digit-classifier: 99.66% test accuracy (Tier 3 could_pass), 64s on MPS, 8 epochs, 468K params
  cifar10-classifier: 91.62% test accuracy (Tier 3 could_pass), 427s on MPS, 25 epochs, 2.2M params
cli_smoke_tested:
  - "zo --version (1.0.2)"
  - "zo --help (branded ZoGroup banner)"
  - "zo init --no-tmux (headless scaffold, .zo/ memory init)"
  - "zo init --no-tmux --dry-run (preview)"
  - "zo init --reset --yes (cleanup)"
  - "zo preflight (6/7 PASS on both plans, only nvidia-smi WARN)"
  - "zo status -p PROJECT --repo PATH (renders status table)"
  - "zo experiments list -p PROJECT --repo PATH (empty registry handled)"
  - "zo experiments / show / diff (subcommand group resolves)"
  - "zo gates set auto/supervised -p PROJECT --repo PATH"
  - "zo migrate --help"
  - "zo watch-training -p PROJECT --repo PATH (Rich Live dashboard renders)"
  - "zo build --help (banner + usage)"
  - "zo continue --help"
  - "zo draft --help"
lint: ruff clean (src/zo/)
validation: scripts/validate-docs.sh 10/10 passed, 1 warning (stale test-count badge — pre-existing)
prs: #22-#25 (UX), #26 (training dashboard + test reports), #27 (draft scout team), #28 (dynamic agents), #29-#33 (init-architect, branded help, website), #34 (tmux timing fix), #39 (preflight integration tests), #41 (notebook directory structure), #44-47 (portable .zo/ memory + --repo flags + confidentiality check + poll-based TUI readiness), #48 (phase snapshots + denylist-first + generic domain-evaluator), #49 (experiment capture layer), #50 (autonomous experiment loop), #51 (brand redesign v2 + website v2 + v1.0.2), #52 (troubleshooting docs), #53 (brand polish + banner consolidation)
