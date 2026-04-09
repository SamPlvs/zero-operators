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
