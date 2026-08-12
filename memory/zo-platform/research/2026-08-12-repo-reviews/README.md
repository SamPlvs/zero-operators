# Repo Deep-Dive Reviews — 2026-08-12

Purpose: thorough review of three agent-orchestration repos to inform a potential
Zero Operators rearchitecture. Requested by Sam; findings feed a rearchitecture
decision session.

## Repos under review (cloned to ~/Documents/code/)

| Repo | Source | Shape |
|------|--------|-------|
| oh-my-claudecode | https://github.com/yeachan-heo/oh-my-claudecode | ~6k files; TypeScript Claude Code plugin ecosystem (agents, hooks, skills, HUD, magic keywords) |
| ruflo | https://github.com/ruvnet/ruflo | ~5.5k files; claude-flow successor, v3; Rust crates + TS, agentdb.rvf, swarm orchestration |
| ralph | https://github.com/snarktank/ralph | 31 files; bash loop + prompt.md autonomous-agent technique, PRD-driven |

## Status

- [x] Repos cloned (2026-08-12)
- [x] Deep-dive workflow complete (9 agents, 63 features catalogued, 0 errors)
- [x] Findings persisted per-repo
- [x] Synthesis + ZO gap analysis persisted (12 ranked adoptions, 6 themes, 11 anti-patterns)
- [x] Rearchitecture decision made (same day): **adopt all 12 features**, five layer-based workstreams, plan at `plans/zo-v2-rearchitecture.md`

## Recovery info (if session dropped)

- Workflow run ID: `wf_64cc6a3c-6fc` (task w15fmlpc9), session e6a7e986-69d1-46cd-817f-1e0760ccc2a9
- Script: `~/.claude/projects/-Users-sam101fe4x-Documents-code-zero-operators/e6a7e986-69d1-46cd-817f-1e0760ccc2a9/workflows/scripts/repo-deep-dive-review-wf_64cc6a3c-6fc.js`
- Agent journal: `.../subagents/workflows/wf_64cc6a3c-6fc/journal.jsonl`
- 8 dive lenses: omcc:orchestration, omcc:components, omcc:runtime, ruflo:core, ruflo:swarm, ruflo:dx, ralph:all, zo-baseline; then 1 synthesis agent.

## Files in this directory

- `oh-my-claudecode.md` — full findings (orchestration, components, runtime UX lenses)
- `ruflo.md` — full findings (core/memory, swarm, plugins/DX lenses)
- `ralph.md` — full findings (complete review)
- `zo-baseline.md` — honest map of ZO's current architecture, strengths, gaps
- `synthesis.md` — cross-repo comparison, ranked features to adopt, rearchitecture themes
- `raw-findings.json` — machine-readable full workflow output (for re-querying)
