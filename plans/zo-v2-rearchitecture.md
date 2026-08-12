# Zero Operators v2 Rearchitecture Plan

---
project_name: "zo-v2-rearchitecture"
version: "1.0"
created: "2026-08-12"
last_modified: "2026-08-12"
status: active
owner: "Sam"
---

## Objective

Rearchitect Zero Operators around the four structural upgrades identified by the
2026-08-12 deep-dive review of three reference systems (see
`memory/zo-platform/research/2026-08-12-repo-reviews/`):

1. **A deterministic enforcement plane below the prompt plane** — hooks that
   mechanically guarantee what spawn prompts currently only promise
   (influence: [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode))
2. **A machine-readable control plane beside the markdown memory** — progress,
   gates, and completion become decidable state, with STATE.md/DECISION_LOG.md
   as the human projection (influence: [ralph](https://github.com/snarktank/ralph))
3. **A fresh-context, disk-state execution substrate** — the failure unit becomes
   one iteration, not one 38-hour session (influence: ralph, hardened with
   oh-my-claudecode's production scar tissue)
4. **An oracle for the platform itself** — the self-evolution loop's "this rule
   would have caught the original failure" becomes a standing CI check
   (influence: [ruflo](https://github.com/ruvnet/ruflo))

All 12 features from the review synthesis ship. Work is organized into five
**layer-based workstreams** (not source-repo categories — features from
different repos interlock into single mechanisms; the repo of origin is
provenance, not architecture).

## Oracle

**Primary metric:** All 12 features land with their per-feature acceptance
criteria passing, and a full demo project (demo-cifar10 rerun) executes
end-to-end with every new mechanism observably firing.

**Ground truth source:** Per-feature seeded-failure tests (each enforcement
mechanism must catch a deliberately planted violation), the platform test
suite, and one full demo run + one production phase (prod-001) on the new
substrate.

**Evaluation method — verification checks:**
1. A seeded contract violation (missing deliverable file) is blocked at SubagentStop
2. A seeded "completion claim + TODO stub in diff" is flagged by the drift guard
3. PreCompact hook flushes state before a forced compaction; STATE.md reflects it
4. PostToolUseFailure produces structured JSONL consumed by the priors pipeline
5. A forged gate approval (echoed tag without nonce) is rejected; a genuine nonce-tagged approval passes
6. A contracted agent's Write/Edit into an off-limits path is denied by the PreToolUse guard reading contracts.json (amended from "disallowedTools" during Phase 1: verifiers need scoped write access — oracle-qa writes oracle/reports/ — and Claude Code has no disallowedTools frontmatter for subagents, so enforcement is path-scoped, keyed on agent identity in the hook input; fail-open when identity is absent)
7. A seeded edit to a sealed eval file is blocked
8. plan-ledger.json generated from plan.md; `zo status` renders from the ledger, not prose parsing
9. A builder attempt to flip `passes: true` is blocked; only oracle-qa's flip lands
10. Plan validation rejects a story with non-verifiable acceptance criteria (sizing lint)
11. An induced 10-minute stall in a test harness is detected by the watchdog and escalated within one poll cycle; a rate-limited session is NOT nudged (never-block taxonomy respected)
12. A rate-limit pause auto-resumes on reset in a controlled test
13. Phase 4 on the fresh-context loop completes demo-cifar10 with results ≥ v1 baseline (91.62%) and total cost ≤ 1.15× v1 baseline
14. Deleting a witness marker from code turns witness-verify red in CI
15. A seeded regression reproducing a PRIORS entry symptom turns its smoke script red
16. README/setup.sh/spec counts are generated from the filesystem; hand-editing a count without the source change turns validate-docs red
17. A refuted prior gets supersededBy front-matter; the digest regenerates; the full PRIORS file is NOT injected at session start (budget check)
18. A pending gate produces exactly one Slack/Telegram notification (cooldown respected); an "approve" reply round-trips into gate passage in a live session
19. `zo hud` renders phase/gate/agents/context from control-plane files only
20. Full demo project end-to-end with all mechanisms enabled: zero regressions in the 854-test platform suite, all new hooks observed firing in comms logs

**Target threshold:**
- Tier 1 (must): checks 1–13 and 20 pass; platform suite green on 3.11 + 3.12; ruff clean; validate-docs 0 failures
- Tier 2 (should): checks 14–17 pass (platform oracle mechanized)
- Tier 3 (could): checks 18–19 pass (operator experience layer)

**Evaluation frequency:** per-feature on PR (seeded-failure test required to
merge — "nothing ships unwired"); per-phase gate review; end-to-end at Phase 6.

**Statistical significance:** Not applicable (deterministic system tests),
except check 13 which compares demo metrics against the recorded v1 baseline.

## Workstreams (layer-based)

| WS | Layer | Features (review rank) | Primary influence |
|----|-------|------------------------|-------------------|
| A | Enforcement plane | Deliverable contracts @ SubagentStop (#1) · Hook-enforced memory (#3) · Nonce approvals (#7) · Trustworthy verifiers (#9) | oh-my-claudecode |
| B | Control plane | plan-ledger.json + oracle-owned pass flags + context-window sizing lint (#4) | ralph + oh-my-claudecode |
| C | Execution substrate | Watchdog from proven parts (#2) · Fresh-context per-subtask loop (#6) | ralph + oh-my-claudecode + ruflo |
| D | Self-learning & platform oracle | Witness manifests + fixture regression (#5) · Smoke tests/ratchets/generated counts (#11) · PRIORS temporal semantics, quality gate, digest, budget (#12) | ruflo |
| E | Operator experience | Two-way notifications (#8) · ZO HUD (#10) | oh-my-claudecode |

## Workflow

**Mode:** platform build (same adapted structure as zero-operators-build.md)

**Phase 1 — Enforcement foundations (WS-A, ~1–2 weeks)**
Contracts compile to `contracts.json` at spawn; SubagentStop validation hook;
workflow-drift-guard regexes; PreCompact/SessionEnd/PostToolUseFailure memory
hooks; disallowedTools on verifiers + sealed-paths PreToolUse check; nonce-tagged
gate approvals. Small, independent, and they de-risk every later phase.
*Gate: verification checks 1–7 pass.*

**Phase 2 — Control plane (WS-B, ~1 week)**
Ledger generator from plan.md; oracle-owned write path; sizing lint in plan
validation; `zo status`/gates/loop-evaluator consume the ledger. STATE.md becomes
a projection for humans, never the parse target for control decisions.
*Gate: checks 8–10 pass.*

**Phase 3 — Execution substrate (WS-C, ~2–3 weeks)**
Watchdog first (heartbeat JSON per agent + external checker in the
LifecycleWrapper poll loop, never-block taxonomy, bounded nudges, rate-limit
wait-and-resume, PID+start-time identity). Then the fresh-context loop for
Phase 4 of the ML workflow: experiment_loop.py spawns a fresh builder per
iteration re-deriving state from ledger + lineage + priors digest; git commit
as checkpoint; validated on demo-cifar10, then prod-001.
*Gate: checks 11–13 pass. Check 13 is the go/no-go for extending fresh-context
to other phases.*

**Phase 4 — Self-learning & platform oracle (WS-D, ~2 weeks)**
PRIORS front-matter (id, status, supersededBy, marker) + three-question quality
gate + generated read-first digest + injection budget; witness-verify (Python,
no signature theater) wired into validate-docs.sh and CI; smoke/ dir with
per-prior reproduction scripts + meta-runner; frontmatter-completeness ratchet;
filesystem-derived counts replacing the hand-maintained cascade numbers.
*Gate: checks 14–17 pass.*

**Phase 5 — Operator experience (WS-E, ~1–2 weeks)**
Outbound notifications (gate-pending, loop verdicts, watchdog alerts; cooldowns)
→ reply-listener with authorization/sanitization copied from OMC's posture →
`zo hud` statusline reading control-plane files.
*Gate: checks 18–19 pass.*

**Phase 6 — Integration validation & retrospective (~1 week)**
Full demo end-to-end with everything enabled; 854-suite + new tests green on
3.11/3.12; retrospective feeding PRIORS; docs cascade.
*Gate: check 20 + Tier 1 threshold.*

## Sequencing rationale

Phases 1–2 are pure additions with no substrate risk and make every later phase
safer (contracts + ledger are what the watchdog and fresh-loop read). Phase 3 is
the only structural change and lands behind a demo-validated gate. Phase 4 is
independent of 3 and can run in parallel if capacity allows. Phase 5 is
deliberately last — it decorates state the earlier phases materialize.

## Anti-scope (from the review's anti-pattern list)

- No keyword-triggered orchestration; spawning stays explicit and imperative
- No hard-blocking Stop as the persistence foundation (fresh spawns + caps instead)
- No mechanism merges without a runtime caller and an observable test ("nothing ships unwired")
- No self-asserted completion anywhere: grading privilege is the oracle's
- No "cryptographic" labels on non-cryptographic guarantees
- Control-plane files live under the existing per-project memory root — no new state roots

## Reference repositories

- **oh-my-claudecode** — https://github.com/yeachan-heo/oh-my-claudecode (enforcement plane, watchdog parts, operator UX)
- **ruflo** — https://github.com/ruvnet/ruflo (witness manifests, smoke-test CI doctrine, temporal memory semantics)
- **ralph** — https://github.com/snarktank/ralph (fresh-context loop, task ledger, story sizing rule)

Full findings: `memory/zo-platform/research/2026-08-12-repo-reviews/` (63
features catalogued with evidence file paths, per-repo verdicts, synthesis).
