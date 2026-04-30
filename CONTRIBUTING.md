# Contributing to Zero Operators

Thanks for your interest. ZO is open-source under the MIT license — issues, fixes, features, and docs all welcome.

---

## Quick start

```bash
git clone https://github.com/SamPlvs/zero-operators.git
cd zero-operators
./setup.sh                     # validates deps, offers to auto-install missing ones
uv sync --extra dev            # editable install + test deps
uv run pytest                  # 740+ tests, all should pass
```

If `setup.sh` flags a missing dep (Claude CLI, tmux, uv), it will offer to install it interactively. Accept or run the printed command yourself.

---

## Development workflow

ZO has a small set of conventions, all checked automatically before each commit.

### Code style

- Python 3.11+, PEP 8, type hints on public APIs
- Google-style docstrings on public functions and classes
- Files under 500 lines, functions under 50 lines
- `uv run ruff check src/` — clean is the bar
- `uv run ruff format src/` — apply formatting fixes

### Tests

- `tests/unit/` — module-level correctness
- `tests/integration/` — cross-module flows
- `tests/fixtures/` — shared fixture plans, target files, mock data

Run before opening a PR:

```bash
uv run pytest                     # full suite
uv run pytest tests/unit/         # fast subset
uv run pytest -k "test_name"      # single test
```

If you're adding a new gate enforcement (artifact requirement, contract check, etc.), include a **negative test** that proves the gate fails when the contract is bypassed. See `PRIORS.md` PR-035 for the rationale.

### Documentation cascade

ZO has a `validate-docs.sh` script that checks documentation matches codebase reality. It's enforced before every commit via a Claude Code PreToolUse hook (when developing inside Claude Code). Run manually any time:

```bash
./scripts/validate-docs.sh
```

When you change a trigger file, update its cascade chain:

| Change | Cascade |
|--------|---------|
| Add/remove agent (`.claude/agents/`) | `setup.sh` EXPECTED_AGENTS, `README.md` badge + roster, `specs/agents.md`, `lead-orchestrator.md`, `plans/zero-operators-build.md`, `PRD.md` |
| Add/remove command (`.claude/commands/`) | `README.md` count, `docs/COMMANDS.md`, `memory/zo-platform/STATE.md` |
| Bump version (`pyproject.toml`) | `src/zo/__init__.py`, `src/zo/cli.py`, `README.md` badge |
| Change agent model tier | `specs/agents.md`, `README.md` roster |

### Commits

Conventional Commits format:

```
feat(orchestrator): add experiment loop policy override
fix(cli): resolve relative target_repo paths to absolute
docs(readme): update agent count after research-scout
chore(deps): bump pydantic to 2.7
```

The pre-commit hook will block commits that fail `validate-docs.sh`.

### Pull requests

Open a PR with:

- A summary of what changed and why (1–3 bullets)
- A test plan (commands you ran, what you verified end-to-end)
- Confirmation that `validate-docs.sh` passes
- A checklist of cascade docs updated (if your change is a trigger)

CI runs `pytest`, `ruff check`, and `validate-docs.sh` on every PR.

---

## Self-evolution protocol

ZO has an unusual convention: **when a bug or failure occurs, update the rule that allowed it, not just the symptom.** See `specs/evolution.md` and `memory/zo-platform/PRIORS.md` for the accumulated examples (currently 35 entries).

If your PR fixes a bug:

1. Add an entry to `memory/zo-platform/PRIORS.md` describing the failure, root cause category (`missing_rule`, `incomplete_rule`, `ignored_rule`, `novel_case`, `regression`), the rule(s) learned, and the verified solution.
2. Cross-reference the prior in the PR description.
3. Where possible, add an enforcement mechanism (test, CI check, hook, gate assertion) so the same class of bug can't recur.

This keeps ZO's institutional knowledge growing instead of repeating mistakes.

---

## Confidentiality (important for contributors who use ZO on real projects)

ZO is a **public repository**. Project-specific information (client names, project names, locations, domain-specific terms, plan contents, oracle thresholds, delivery repo paths) MUST NEVER appear in any tracked file. This is enforced by `validate-docs.sh` Check 8.

The check reads patterns from a **gitignored** file at `scripts/.client-blocklist` (one pattern per line, comments allowed). When working on a real project:

1. Append your project's identifying patterns to your local `scripts/.client-blocklist` (the file is already in `.gitignore`)
2. Use the alias convention in tracked files: `prod-001`, `prod-002`, ... for production projects; `demo-mnist`, `demo-cifar10`, ... for demos
3. Keep the alias → real-name mapping only in `memory/{project}/` (gitignored) — never in `memory/zo-platform/` (tracked)
4. PR descriptions and commit messages must also use aliases — `validate-docs.sh` only catches file contents, not git messages

If you spot a client identifier in a tracked file, remove it immediately. See `CLAUDE.md` "Client Project Confidentiality" section.

---

## Reporting issues

- **Bugs**: open an issue using the bug report template
- **Feature requests**: use the feature request template
- **Security vulnerabilities**: please open a private security advisory at <https://github.com/SamPlvs/zero-operators/security/advisories/new> rather than a public issue

---

## Code of Conduct

Be kind. Discriminatory, harassing, or hostile behaviour will not be tolerated. We follow the spirit of the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

---

## License

ZO is MIT-licensed (see `pyproject.toml`). By contributing, you agree that your contributions will be licensed under the same terms.
