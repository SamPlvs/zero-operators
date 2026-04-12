# Custom Agents

Project-specific specialist agents created during `zo draft` or `zo build`.

## How They Get Here

1. **Plan-defined** — the Plan Architect suggests custom agents during `zo draft`, written into plan.md's `## Agent Configuration` section. The orchestrator auto-creates the `.md` files here at build start.

2. **Mid-build** — the Lead Orchestrator identifies an expertise gap during execution and creates a specialist on the fly. Logged to DECISION_LOG.

## Reuse

Custom agents persist across projects. The orchestrator scans this directory and includes custom agents in the roster prompt. If a future project has a similar domain, the lead can reuse existing specialists instead of creating new ones.

## Format

Same as core agents in `.claude/agents/`:

```yaml
---
name: Agent Display Name
model: claude-sonnet-4-6
role: One-line description
tier: phase-in
team: project
---
```

Followed by: role description, coordination rules, validation checklist.

## Not Limited

Custom agents can be any role — domain specialists, data scientists, signal processing experts, security auditors, calibration engineers, NLP researchers, testing specialists, etc. The team adapts to the project.
