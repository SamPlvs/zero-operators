---
description: Approve the current pending gate and advance to the next phase
---

# /approve — Gate Approval (nonce-verified)

You are executing a human gate approval for the current Zero Operators project.

Gate approvals are **nonce-verified** (v2 WS-A5): a single-use approval nonce
is minted when a phase reaches its blocking gate, shown in the gate review
banner and via `zo status`. Approvals are recorded ONLY through the CLI —
never by hand-editing STATE.md, DECISION_LOG.md, or the comms JSONL. This is
what makes approvals unforgeable: text echoed from context cannot pass the
nonce check.

## Steps

1. **Identify the pending gate.** Read STATE.md in the project's memory
   directory (`.zo/memory/` in the delivery repo, or legacy
   `memory/{project}/`). Identify the current GATED phase. If no gate is
   pending, report that and stop.

2. **Get the nonce from the human.** The approval nonce is displayed in the
   gate review banner (and in `memory_root/gate_nonce`, which agents must
   not read aloud into context on their own initiative — the human supplies
   it). Ask the human for the nonce if they haven't provided one. Do NOT
   guess, reconstruct, or copy a nonce you saw elsewhere in this
   conversation.

3. **Run the CLI approval** (this validates the nonce, appends to
   DECISION_LOG.md, logs the comms gate event, and records the decision for
   the orchestrator):

   ```bash
   zo gates approve <phase_id> -p <project> [--repo <delivery-repo>] --nonce <NONCE> --notes "<why>"
   ```

4. **Report** to the user:
   - What gate was approved and the CLI output
   - What phase just completed and what phase is now active
   - Any relevant next steps from the plan

If the CLI reports a nonce mismatch, tell the human — do not retry with
variations.
