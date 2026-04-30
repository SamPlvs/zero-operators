# Changelog

All notable changes to Zero Operators are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [1.0.2] — 2026-04

### Added

- `--low-token` cost-saving preset for Anthropic Pro / student / budget-watching plans. Sets Sonnet lead, Haiku for code-reviewer / test-engineer / oracle-qa, max 2 Phase-4 iterations, full-auto gates, and earlier auto-compaction. CLI flag and plan YAML field both supported. Override individual knobs with `--lead-model`, `--max-iterations`, `--no-headlines`. ([#54]–[#61])
- Brand v2: new palette (canvas / paper / coral / dusk / moss), typography (Geist + Cormorant Garamond + JetBrains Mono), and simplified C mark replacing the orbital mark. ([#51])
- Website v2: Astro 5 single-page static, mobile-tested, light/dark theme toggle. ([#51])
- Phase completion snapshots — `.zo/snapshots/` capture state at every gate transition. ([#48])
- Experiment capture layer — `.zo/experiments/` registry with hypothesis → config → metrics → result lineage per Phase 4 iteration. ([#49])
- Autonomous experiment loop — non-supervised modes auto-iterate Phase 4 with target / budget / plateau / dead-end detection. Plan-level `## Experiment Loop` block for per-project overrides. ([#50])
- `ZOTrainingCallback` hard gate enforcement — Phase 4 fails if `metrics.jsonl` and `training_status.json` aren't produced. ([#59])
- Platform-aware Docker scaffold — auto-detects GPU vs CPU host and emits the appropriate compose template. ([#48])
- `docs/TROUBLESHOOTING.md` — covers spawn crashes, tmux paste timing, build appearing stuck, worktree confusion, bash 3.2 silent failures. ([#52])
- `docs/reference/cost-benchmark.mdx` — measured methodology and ~30 % reduction on the canonical reference run with `--low-token` (lead-only swap). ([#60])
- `docs/concepts/low-token-mode.mdx` — preset table, trade-offs, FAQ. ([#54])

### Changed

- README banner consolidated into `design/banner/`. ([#53])
- Sub-agents in `--low-token` mode now route to Haiku where appropriate; Phase 1 trimmed to data-engineer only; Phase 5 trimmed to model-builder + oracle-qa only. ([#61])
- README framing updated to remove dataset-specific benchmark wording. ([#63])

### Fixed

- MDX 2 parser bug rendering `<500 lines` and `<1 pp` as JSX tags on the docs site. ([#62])
- Doc site stale-cache 404 on the legacy `/concepts/agents` slug — redirect added to `/concepts/the-team`. ([#56])
- `zo continue --repo` not threading delivery-repo hint through to `build()`; `gates set` and `watch-training` also gained `--repo`. ([#46])
- macOS Docker compose template now emits CPU runtime when no GPU is detected, instead of failing on `device driver` selection. ([#48])

---

## [1.0.1] — 2026-04

### Added

- Interactive tmux agent sessions (send-keys + paste-buffer) — agents are visible in tmux panes during `zo build`.
- ZO brand panel banner at startup (project, mode, phase, gate info) on every CLI command.
- Smart `zo build` mode detection — auto-detects fresh / continue / plan-edited and re-decomposes when the plan changes.
- Pre-launch phase review (subtasks, agents, oracle criteria) before agent team launches.
- Live monitoring dashboard — tasks, team status, comms events.
- Doc-code consistency validator (`scripts/validate-docs.sh`) with PreToolUse hook enforcement on commit.
- Self-evolution: PR-005 enforcement-over-aspiration with three-layer defense against doc drift.
- **Research Scout** agent — cross-cutting on all phases for literature review and prior-art surveys.
- `zo draft` accepts multiple file/dir paths plus interactive refinement.
- Hook system: SessionStart, PreToolUse, PostToolUse, Stop.

### Removed

- `zo maintain` — collapsed into `zo build`, which now detects plan edits and re-decomposes. `zo continue` is a thin alias.

---

## [1.0.0] — 2026-04

Initial public release.

### Added

- 17 agent definitions (11 project delivery + 6 platform build), Claude Code native agent teams.
- Plan parser with 8-section schema validation.
- Target parser with isolation enforcement (zo_only_paths blocklist).
- Memory layer — STATE.md, DECISION_LOG.md, PRIORS.md, sessions/, with atomic writes.
- Semantic index — fastembed + SQLite, full decision entries with summary prefix.
- Hybrid orchestration engine — Python lifecycle wrapper invokes `claude` CLI; agents communicate peer-to-peer via Claude Code's native team capability.
- JSONL comms logger with five event types (message, decision, gate, error, checkpoint), daily rotation.
- Evolution engine — post-mortem protocol, root cause categorization, automated PRIORS updates.
- CLI: `zo build`, `zo continue`, `zo draft`, `zo init`, `zo status`, `zo preflight`.
- 24 slash commands across 8 categories (platform, project, memory, gates, observe, document, agents, utility).
- E2E validation passed on canonical reference projects (full ML lifecycle).
- All 8 PRD §9 acceptance criteria met.

[Unreleased]: https://github.com/SamPlvs/zero-operators/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/SamPlvs/zero-operators/releases/tag/v1.0.2
[1.0.1]: https://github.com/SamPlvs/zero-operators/releases/tag/v1.0.1
[1.0.0]: https://github.com/SamPlvs/zero-operators/releases/tag/v1.0.0
[#46]: https://github.com/SamPlvs/zero-operators/pull/46
[#48]: https://github.com/SamPlvs/zero-operators/pull/48
[#49]: https://github.com/SamPlvs/zero-operators/pull/49
[#50]: https://github.com/SamPlvs/zero-operators/pull/50
[#51]: https://github.com/SamPlvs/zero-operators/pull/51
[#52]: https://github.com/SamPlvs/zero-operators/pull/52
[#53]: https://github.com/SamPlvs/zero-operators/pull/53
[#54]: https://github.com/SamPlvs/zero-operators/pull/54
[#56]: https://github.com/SamPlvs/zero-operators/pull/56
[#59]: https://github.com/SamPlvs/zero-operators/pull/59
[#60]: https://github.com/SamPlvs/zero-operators/pull/60
[#61]: https://github.com/SamPlvs/zero-operators/pull/61
[#62]: https://github.com/SamPlvs/zero-operators/pull/62
[#63]: https://github.com/SamPlvs/zero-operators/pull/63
