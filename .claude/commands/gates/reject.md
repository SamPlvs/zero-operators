---
description: Reject the current pending gate with a reason, triggering rework
argument-hint: <reason>
---

# /reject — Gate Rejection (nonce-verified)

You are executing a human gate rejection for the current Zero Operators
project. The argument provided is the rejection reason.

Gate decisions are **nonce-verified** (v2 WS-A5) and recorded ONLY through
the CLI — never by hand-editing STATE.md, DECISION_LOG.md, or the comms
JSONL. Text echoed from context cannot pass the nonce check.

## Steps

1. **Identify the pending gate.** Read STATE.md in the project's memory
   directory (`.zo/memory/` in the delivery repo, or legacy
   `memory/{project}/`). Identify the current GATED phase. If no gate is
   pending, report that and stop.

2. **Get the nonce from the human.** The approval nonce is shown in the gate
   review banner. Ask the human for it if not provided. Do NOT guess,
   reconstruct, or copy a nonce you saw elsewhere in this conversation.

3. **Run the CLI rejection** (validates the nonce, appends to
   DECISION_LOG.md, logs the comms gate event, and records the iterate
   decision for the orchestrator — the phase returns to ACTIVE for rework):

   ```bash
   zo gates reject <phase_id> -p <project> [--repo <delivery-repo>] --nonce <NONCE> --reason "$ARGUMENTS"
   ```

4. **Report** to the user:
   - What gate was rejected and why (the CLI output)
   - The phase is now set back to ACTIVE for rework
   - What the agents need to address based on the rejection reason
   - Suggested next steps (re-run the phase, modify approach, etc.)

If the CLI reports a nonce mismatch, tell the human — do not retry with
variations.
