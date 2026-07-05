# Watchdog / Heartbeat — anti-stall for long-running autonomous runs

**Status:** design spec (RFC). Implementation tracked as the follow-up to this PR.
**Owner:** core / orchestrator.
**Motivation:** a real failure mode observed in a long autonomous run — the whole team stalled *silently for ~38 hours* and nobody noticed until the human asked "where are we?".

---

## 1. The failure mode

ZO's lead-orchestrator is **event-driven**: it acts when it receives a message (from the human or from a teammate agent). This is efficient, but it has a silent-death hole:

- When every teammate agent finishes its immediate task and goes **idle** (or dies silently), no teammate message is emitted.
- The orchestrator therefore receives **no wake signal**, so it is never re-invoked.
- A long **background job** (a training run, a sweep, an external CI/deploy) emits no agent message while it runs — and if its launcher dies, nothing reports it.
- Net: "wait for the next message" silently degrades into **"do nothing, indefinitely."** The run looks alive (no error) but has flat-lined.

Contributing factors seen in the wild:
- A dedicated monitor agent (a "context-warden") is itself a single point of failure — it can die silently too, taking the only liveness check with it.
- No-news is read as progress. Absence of an error is not evidence of forward motion.

This is distinct from context-window saturation (already handled by checkpoint→respawn). This is **idle-stall**: healthy-looking agents that have simply stopped moving the work forward.

---

## 2. Requirements

1. **Active heartbeat, not passive wait.** The run must have a wake source that fires on a wall-clock schedule independent of teammate messages, so an all-idle team cannot go unnoticed.
2. **Liveness by evidence, not by silence.** Detect progress from observable state (process is running, output files/heartbeats advancing), never from "no bad message arrived."
3. **Auto-remediation.** On a detected stall, re-mobilize (nudge/respawn the responsible agent, re-issue its task) rather than only alerting.
4. **No single point of failure.** The heartbeat is owned by the orchestrator/run itself, not by one killable monitor agent.
5. **Survives session boundaries.** Session-scoped timers (cron/wakeup) are re-armed at the start of every session; the *policy* lives in durable config so a fresh session re-establishes the watch automatically.
6. **Cheap + quiet.** Low token/compute cost; only speaks when it detects a stall or a state change, not on every tick.

---

## 3. Design

### 3.1 Heartbeat tick (scheduled self-invoke)
A recurring, off-minute schedule (default `*/17 * * * *` — ~every 17 min, jittered, never on `:00`) enqueues a **watchdog tick** prompt to the orchestrator. Session-scoped by nature, so it is re-armed on session start from `project_config`. This is the wake source that closes the "all-idle → never re-invoked" hole.

### 3.2 Liveness probe (evidence-based)
Each tick evaluates, per active agent / critical-path job:
- **Agent liveness:** heartbeat file mtime fresh (< `stall_threshold`, default 20 min) AND/OR a live owned process.
- **Job liveness:** the real process PID is running (not just a wrapper/launcher that already exited); output artifacts advancing (new/growing files since last tick).
- **Progress delta:** did any tracked artifact change since the previous tick?

A **stall** = no progress delta AND no live critical-path process for ≥ N consecutive ticks (default N=1 for a hard stall, N=2 for a soft one).

### 3.3 Long-job monitor (event stream)
For a specific long-running job, attach a streaming monitor on its log with a filter covering **both** progress and failure signatures (`epoch|elapsed|wrote|saved|Traceback|Error|FAILED|Killed|OOM|nan`). Silence-is-not-success: a filter that matches only the happy path stays quiet through a crashloop. This gives immediate notification on crash/completion between heartbeat ticks.

### 3.4 Remediation policy
On stall detection the watchdog escalates by policy:
1. **Nudge** the responsible agent (re-send its outstanding task).
2. If still dead next tick → **respawn** it from its on-disk resume/checkpoint and re-issue.
3. Prefer a **reliable executor**: if an agent role has failed to engage repeatedly (e.g., two silent dead spawns), route its critical-path task to a known-reliable agent instead of retrying the same role. Log the reroute.
4. **Never silently truncate**: every stall, reroute, and dropped item is logged and surfaced to the human at the next checkpoint.

### 3.5 Configuration (`project_config`)
```
watchdog:
  enabled: true
  tick_cron: "*/17 * * * *"     # off-minute; re-armed each session
  stall_threshold_min: 20        # heartbeat/artifact staleness => suspect
  stall_ticks_hard: 1            # no-process + no-progress => stall now
  stall_ticks_soft: 2            # progress-but-slow => stall after N ticks
  remediation: [nudge, respawn, reroute]
  monitor_failure_signatures: ["Traceback","Error","FAILED","Killed","OOM","nan"]
```

---

## 4. Integration points
- **`orchestrator.py`** — arm the heartbeat cron on run/session start (re-arm if a prior schedule is gone); own the watchdog-tick handler.
- **`comms.py`** — the watchdog reads agent heartbeats + emits nudge/respawn messages through the existing comms bus.
- **`.claude/agents/lead-orchestrator.md`** — add the standing rule: never end a turn in passive "hold and wait" while critical-path work is outstanding; a heartbeat must be armed. Verify liveness by evidence (pgrep the real PID, artifact deltas), not by absence of bad news.
- **`project_config.py`** — the `watchdog:` block above; default-on.
- A dedicated monitor agent (if any) becomes a *helper*, not the sole mechanism — the orchestrator-owned heartbeat is the backstop.

---

## 5. Acceptance / tests
- Unit: stall-detection predicate (fresh vs stale heartbeat; live vs dead PID; progress delta present/absent) → correct hard/soft/no-stall classification.
- Unit: remediation escalation (nudge → respawn → reroute) state machine.
- Unit: config parse + defaults + re-arm idempotency (arming twice doesn't double-schedule).
- Integration: simulate an all-idle team with no progress across ticks → watchdog fires remediation; simulate a live-but-slow job → no false stall.
- Regression: the failure-signature filter matches a crashloop/OOM sample (silence-is-not-success guard).

---

## 6. Out of scope (this PR is spec-only)
Code, tests, and orchestrator wiring land in the follow-up implementation PR against this spec. Context-window saturation handling (checkpoint→respawn) already exists and is unchanged — this feature covers **idle-stall**, the orthogonal hole.
