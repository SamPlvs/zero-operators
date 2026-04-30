## Summary

<!-- 1–3 bullets: what changed and why. Focus on the "why". -->

## Type

- [ ] feat — new feature
- [ ] fix — bug fix
- [ ] docs — documentation only
- [ ] refactor — no behaviour change
- [ ] perf — performance improvement
- [ ] test — test changes only
- [ ] chore — tooling, deps, etc.

## Test plan

- [ ] `uv run pytest` passes locally
- [ ] `uv run ruff check src/` is clean
- [ ] `./scripts/validate-docs.sh` passes (or warning is pre-existing)
- [ ] Manual verification:

<!-- Describe what you ran end-to-end. For UI / CLI changes, paste output. -->

## Cascade docs

If this PR adds/removes an agent, command, version bump, or model tier, confirm:

- [ ] Agent change → updated `setup.sh` (EXPECTED_AGENTS), `README.md` (badge + roster), `specs/agents.md`, `lead-orchestrator.md`, `plans/zero-operators-build.md`, `PRD.md`
- [ ] Command change → updated `README.md`, `docs/COMMANDS.md`, `STATE.md`
- [ ] Version bump → updated `pyproject.toml`, `__init__.py`, `cli.py`, `README.md` badge, `CHANGELOG.md`
- [ ] Model tier change → updated `specs/agents.md`, `README.md` roster

## Self-evolution (if fixing a bug)

- [ ] Added a `memory/zo-platform/PRIORS.md` entry for the failure (root cause + rule learned)
- [ ] Added an enforcement mechanism (test, hook, CI check, gate assertion) so this class of bug can't recur

## Confidentiality

- [ ] No client-identifying content in code, comments, commit messages, or this PR description
- [ ] Project aliases used (`prod-001`, `demo-mnist`, ...) where any project example is needed

## Related

<!-- Closes #XX, refs #YY, related to PRIORS PR-NN -->
