# Security Policy

Thank you for helping keep Zero Operators users safe.

## Supported versions

Active support tracks the latest minor release. Older minors receive security fixes on a best-effort basis only.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Open a private security advisory instead:

<https://github.com/SamPlvs/zero-operators/security/advisories/new>

Include:

- A description of the issue and its impact
- Steps to reproduce (or a proof-of-concept)
- Affected versions / commits
- Any proposed mitigations

## What to expect

- **Acknowledgement** within 72 hours of report
- **Initial assessment** (severity, scope, affected versions) within 7 days
- **Patch + advisory** as soon as practical — typically 14–30 days for routine issues; longer for ones requiring coordinated disclosure

We follow standard coordinated-disclosure practice: a fix is prepared, an advisory is drafted, both ship together, and credit is given to the reporter (unless they prefer to remain anonymous).

## In scope

- Path traversal or injection in `plan.py`, `target.py`, `scaffold.py`, or other writers that take user-supplied paths
- Privilege escalation via agent prompt injection or via the wrapper's tmux/CLI surface
- Information disclosure — credentials, secrets, or client identifiers leaking into logs, JSONL comms, `DECISION_LOG.md`, or generated artifacts
- Confidentiality bypasses in the `.gitignore` / `validate-docs.sh` blocklist enforcement
- Supply-chain risk in our direct dependencies where ZO's usage is the trigger

## Out of scope

- Issues affecting forks of ZO with substantial modifications
- Findings from automated scanners with no demonstrated exploit
- Vulnerabilities in third-party dependencies — please report those upstream first; we'll respond to indirect impact via dependency updates
- Social engineering, physical attacks, or denial-of-service via legitimate API usage

Thank you for disclosing responsibly.
