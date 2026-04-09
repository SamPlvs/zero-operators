# DECISION_LOG — Zero Operators Platform Build

Append-only. Every orchestration decision with timestamp, rationale, and outcome.

---

## Decision: 2026-04-09T16:00:00Z
**Type:** ARCHITECTURE
**Title:** Orchestration approach — Hybrid
**Decision:** Use Claude Code native agent teams for peer-to-peer communication + Python lifecycle wrapper that invokes `claude` CLI, captures lifecycle events, and pipes to JSONL comms logger.
**Rationale:** Native agent teams provide the best communication model (peer-to-peer is the superpower). Python wrapper adds observability without interfering with communication.
**Alternatives considered:** (1) Pure native — less control over logging/lifecycle. (2) Pure Python subprocess — loses peer-to-peer comms.
**Outcome:** Documented in build plan v2.0 as RD1.

---

## Decision: 2026-04-09T16:05:00Z
**Type:** ARCHITECTURE
**Title:** Semantic index granularity — Full entries with summary prefix
**Decision:** One vector per DECISION_LOG entry. Extract 1-line summary from title + outcome at index time. Summary embedded for matching; full entry returned on retrieval.
**Rationale:** Optimizes for context-window density. 3 highly relevant full decisions > 10 noisy fragments.
**Alternatives considered:** (1) Sentence-level splits — too noisy. (2) Paragraph-level — fragments rationale from decision. (3) Defer to v1.1 — loses the value of semantic search.
**Outcome:** Documented in build plan v2.0 as RD2.

---

## Decision: 2026-04-09T16:10:00Z
**Type:** SCOPE
**Title:** zo draft in v1 — Yes, with document indexing
**Decision:** Include `zo draft <source-dir>` in v1 CLI. Takes source docs, indexes them (project-scoped, persisted), generates compliant plan.md.
**Rationale:** Plan drafting is core to the human experience. Without it, every project requires manual plan authoring against a complex 8-section schema.
**Alternatives considered:** Defer to v1.1 — but plan quality directly impacts ZO effectiveness.
**Outcome:** Documented in build plan v2.0 as RD3.

---

## Decision: 2026-04-09T16:15:00Z
**Type:** SCOPE
**Title:** Dashboard API deferred to v2
**Decision:** No API design in v1. CLI + files only.
**Rationale:** Premature API design without frontend to drive requirements leads to wrong abstractions.
**Outcome:** Documented in build plan v2.0 as RD4.

---

## Decision: 2026-04-09T16:20:00Z
**Type:** ARCHITECTURE
**Title:** Agent definition contracts — Inline + shared reference
**Decision:** Each agent .md has a minimal inline contract example + pointer to specs/agents.md for full template.
**Rationale:** Inline makes agents self-contained. Shared reference prevents duplication and ensures consistency.
**Outcome:** Documented in build plan v2.0 as RD5.

---

## Decision: 2026-04-09T16:25:00Z
**Type:** SCOPE
**Title:** Docker deferred to v2
**Decision:** Use uv lockfile + setup.sh for reproducibility. No Docker in v1.
**Rationale:** Single-developer platform build doesn't benefit enough from Docker to justify the complexity. uv lockfile provides deterministic deps.
**Outcome:** Documented in build plan v2.0 as RD6.

---

## Decision: 2026-04-09T16:30:00Z
**Type:** ARCHITECTURE
**Title:** Setup tooling — Both setup.sh + zo init
**Decision:** `setup.sh` for environment bootstrap (claude CLI, agent teams, deps). `zo init` for project scaffolding (memory files, template plan.md).
**Rationale:** Different concerns at different times. setup.sh runs once per environment. zo init runs once per project.
**Outcome:** Documented in build plan v2.0 as RD7.

---

## Decision: 2026-04-09T16:35:00Z
**Type:** SEQUENCING
**Title:** Agent definitions as Step 0
**Decision:** Write all 16 agent .md files before any Python code.
**Rationale:** (1) Immediately usable by Claude Code. (2) Define contracts all modules implement against. (3) Platform build agents needed to build ZO itself. (4) Forces finalization of every agent interface.
**Outcome:** Phase 0 added to build sequence. Documented in build plan v2.0 as RD8.

---

## Decision: 2026-04-09T17:15:00Z
**Type:** MILESTONE
**Title:** Phase 0 complete — 16 agents written
**Decision:** All 16 agent definition files written to .claude/agents/. Settings.json created. Build plan updated to v2.0.
**Rationale:** Phase 0 deliverables met: 10 project delivery agents (6 launch + 4 phase-in) + 6 platform build agents. Each has YAML frontmatter, role description, ownership, off-limits, contract produced/consumed with inline examples, pointer to specs/agents.md, coordination rules, validation checklist.
**Outcome:** Gate 0 ready for human verification. Phase 1 unblocked.

---

## Decision: 2026-04-09T17:30:00Z
**Type:** GATE
**Title:** Gate 0 passed — Human approved agent definitions
**Decision:** PROCEED to Phase 1
**Rationale:** Sam reviewed and approved all 16 agent definitions and .claude/settings.json.
**Outcome:** Phase 1 (Scaffolding) unblocked.

---

## Decision: 2026-04-09T18:00:00Z
**Type:** GATE
**Title:** Gate 1 passed — Phase 1 modules complete
**Decision:** PROCEED to Phase 2
**Rationale:** All 4 Phase 1 modules built and tested. 76 tests passing, 97% code coverage, ruff lint clean. Modules: plan parser (src/zo/plan.py), target parser (src/zo/target.py), comms logger (src/zo/comms.py), setup.sh. PyYAML added as dependency.
**Outcome:** Phase 2 (Core Infrastructure) unblocked.

---

## Decision: 2026-04-09T18:30:00Z
**Type:** ARCHITECTURE
**Title:** Memory layer — three-file split for 500-line limit
**Decision:** Split memory module into memory.py (292 lines), _memory_models.py (89 lines), _memory_formats.py (285 lines).
**Rationale:** Single file would exceed 500-line limit. Models have zero deps beyond pydantic, formats depend only on models, memory.py re-exports everything for clean imports.
**Outcome:** Clean separation, all tests pass.

---

## Decision: 2026-04-09T18:45:00Z
**Type:** ARCHITECTURE
**Title:** Semantic index — graceful fallback without fastembed
**Decision:** When fastembed/numpy are not installed, store entries without embeddings and fall back to word-overlap scoring on summaries for query().
**Rationale:** fastembed is an optional dependency. Core ZO must function without it. Word-overlap is a reasonable fallback for small decision sets.
**Outcome:** 25 tests run without fastembed, 7 additional tests verify embedding path. Both paths verified.

---

## Decision: 2026-04-09T19:00:00Z
**Type:** GATE
**Title:** Phase 2 complete — Gate 2 ready for human review
**Decision:** Memory layer and semantic index both built, tested, and verified.
**Rationale:** 151 tests passing (32 memory + 32 semantic + 76 Phase 1 + 11 integration), 96% coverage, ruff clean. End-to-end smoke test demonstrates full lifecycle: initialize → write state → log decisions → add priors → write summary → build index → semantic query → session recovery.
**Outcome:** Gate 2 ready for human review. Phase 3 (Orchestration Engine) unblocked pending approval.

---

## Decision: 2026-04-09T19:00:00Z
**Type:** ARCHITECTURE
**Title:** Wrapper redesign — observer/launcher, not agent spawner
**Decision:** wrapper.py launches ONE Claude Code session (the Lead Orchestrator), does NOT spawn individual agents via subprocess. The Lead Orchestrator creates the team internally using TeamCreate + Agent(team_name=...). Wrapper monitors via file system (tasks, logs, tmux).
**Rationale:** Research confirmed that Claude Code agent teams with peer-to-peer comms (SendMessage) can only be created from WITHIN a running Claude Code session, not via external CLI calls. Previous design of wrapper.py spawning N individual agents would have produced isolated sessions without peer-to-peer messaging — defeating the core requirement.
**Alternatives considered:** (1) N subprocess calls per agent (no peer-to-peer). (2) Custom file-based messaging (fragile, not native). (3) Single session with TeamCreate (chosen — leverages native peer-to-peer).
**Outcome:** wrapper.py redesigned as observer/launcher. orchestrator.py builds the lead prompt. Lead Orchestrator agent definition updated with 16-agent roster and dynamic agent creation capability.

---

## Decision: 2026-04-09T19:10:00Z
**Type:** ARCHITECTURE
**Title:** Lead Orchestrator — dynamic agent creation
**Decision:** Lead Orchestrator can create new agent definition files (.claude/agents/*.md) on the fly if a project requires expertise not covered by the 16 pre-defined agents.
**Rationale:** The agent roster is a starting point, not a ceiling. Real projects will need domain-specific experts (NLP specialist, time-series expert, security auditor). The Lead Orchestrator has the context to identify gaps and write appropriate agent definitions following the established template.
**Outcome:** lead-orchestrator.md updated with agent roster table and dynamic creation protocol.

---

## Decision: 2026-04-09T19:30:00Z
**Type:** GATE
**Title:** Phase 3 complete — Orchestration engine + wrapper built
**Decision:** PROCEED to Phase 4
**Rationale:** 224 tests passing, 93% coverage, ruff clean. Orchestrator decomposes plans into phases for all 3 workflow modes, generates agent contracts, builds lead prompts with full context. Wrapper launches sessions, monitors teams, handles rate limits. Architecture validated: Python CLI → one Claude session → native agent team with peer-to-peer comms.
**Outcome:** Phase 4 (Hardening — Evolution Engine, CLI, integration tests) unblocked.

---

## Decision: 2026-04-09T20:00:00Z
**Type:** GATE
**Title:** Phase 4 complete — Evolution engine, CLI, integration tests
**Decision:** PROCEED to Phase 5
**Rationale:** 296 tests passing, 90% coverage, ruff clean. Evolution engine implements full post-mortem protocol (5 steps), retrospective, and metrics. CLI provides zo build/continue/maintain/init/status/draft with gate mode toggle (default: supervised). Integration tests verify full pipeline flows. All modules wired together.
**Outcome:** Phase 5 (End-to-end validation) unblocked.

---

## Decision: 2026-04-09T20:30:00Z
**Type:** ARCHITECTURE
**Title:** Wrapper CLI flags corrected — --cwd and --teammate-mode don't exist
**Decision:** Replace `--cwd` with `--add-dir` for delivery repo access. Remove `--teammate-mode tmux` (non-existent flag). Add `--dangerously-skip-permissions` for non-interactive execution.
**Rationale:** First live run failed with "error: unknown option '--cwd'". Investigation showed these flags don't exist in the claude CLI. `--add-dir` grants file access to additional directories. Teams are created internally via TeamCreate, not via CLI flag.
**Alternatives considered:** (1) Use subprocess cwd parameter — doesn't work because claude needs to run from ZO root. (2) Symlinks — fragile. (3) --add-dir — correct approach, grants access without changing working directory.
**Outcome:** First successful live run of ZO. MNIST Phase 1 completed.

---

## Decision: 2026-04-09T21:00:00Z
**Type:** GATE
**Title:** Phase 5 complete — MNIST end-to-end validation passed
**Decision:** ZO platform validated. Ready for real projects.
**Rationale:** MNIST digit classifier built autonomously across 5 phases. 99.00% test accuracy (Tier 1 threshold: 95%). Agent team produced model, inference script, oracle evaluation, GradCAM/saliency XAI, ablation study, significance testing, reproducibility verification. 98 tests in delivery repo. Zero ZO artifacts. 4 clean git commits. Total cost ~$11.
**Known issues:** (1) Phase state not persisted between zo build calls — lead session re-discovers resume point from delivery repo. (2) Blocking gates cause repeated sessions in auto mode. Both are hardening items, not blockers.
**Outcome:** ZO is production-ready for real projects. IVL F5 is next.
