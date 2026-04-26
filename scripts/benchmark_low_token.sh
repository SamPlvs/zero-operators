#!/usr/bin/env bash
# benchmark_low_token.sh — measure token cost reduction from --low-token mode.
#
# Runs `zo build` against the MNIST plan twice (default mode + low-token mode),
# captures Claude Code token usage via `npx ccusage`, and writes a comparison
# JSON + console summary.
#
# Prerequisites:
#   - `zo` CLI installed (this repo, ./setup.sh)
#   - `claude` CLI logged in
#   - `npx ccusage` available (npm install -g ccusage)
#   - Mac or Linux dev box (Apple Silicon recommended for ~25min low-token wall time)
#   - ~75 minutes wall time, ~$13-14 spend on Anthropic API
#
# Usage:
#   ./scripts/benchmark_low_token.sh
#   ./scripts/benchmark_low_token.sh --delivery-prefix /tmp/zo-bench
#   ./scripts/benchmark_low_token.sh --skip-default --skip-low-token  # dry preview
#   ./scripts/benchmark_low_token.sh --help
#
# Output:
#   benchmark-results-{ISO-timestamp}.json — full diff + summary
#   stdout — human-readable summary table

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & arg parsing
# ---------------------------------------------------------------------------

DELIVERY_PREFIX="${TMPDIR:-/tmp}/zo-low-token-bench"
RUN_DEFAULT=true
RUN_LOW_TOKEN=true
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
RESULT_FILE="benchmark-results-${TIMESTAMP}.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --delivery-prefix)
      DELIVERY_PREFIX="$2"; shift 2 ;;
    --skip-default)
      RUN_DEFAULT=false; shift ;;
    --skip-low-token)
      RUN_LOW_TOKEN=false; shift ;;
    --help|-h)
      grep '^# ' "$0" | sed 's/^# //'
      exit 0 ;;
    *)
      echo "Unknown arg: $1" >&2
      echo "Run with --help for usage." >&2
      exit 2 ;;
  esac
done

DEFAULT_DELIVERY="${DELIVERY_PREFIX}-default"
LOW_TOKEN_DELIVERY="${DELIVERY_PREFIX}-low-token"
PLAN_PATH="plans/mnist-digit-classifier.md"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

step() {
  printf "\n\033[38;2;240;192;64m▸ %s\033[0m\n" "$*"
}

ok() {
  printf "  \033[38;2;80;200;80m✓\033[0m %s\n" "$*"
}

fail() {
  printf "  \033[38;2;240;80;80m✗\033[0m %s\n" "$*"
  exit 1
}

step "Pre-flight checks"

command -v zo >/dev/null 2>&1 || fail "zo CLI not found on PATH (run ./setup.sh)"
ok "zo CLI: $(zo --version 2>&1 | head -1)"

command -v claude >/dev/null 2>&1 || fail "claude CLI not found on PATH"
ok "claude CLI: $(claude --version 2>&1 | head -1 || echo 'present')"

if command -v npx >/dev/null 2>&1; then
  ok "npx available — will use ccusage for token totals"
  CCUSAGE_AVAILABLE=true
else
  printf "  \033[38;2;240;192;64m⚠\033[0m  npx not found — falling back to manual JSONL parsing\n"
  CCUSAGE_AVAILABLE=false
fi

[[ -f "$PLAN_PATH" ]] || fail "MNIST plan not found at $PLAN_PATH (run from ZO repo root)"
ok "MNIST plan: $PLAN_PATH"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ccusage_snapshot() {
  # Capture current daily usage as a JSON blob via ccusage.
  # Fallback: capture sizeof concat of today's JSONL for a rough proxy.
  if [[ "$CCUSAGE_AVAILABLE" == "true" ]]; then
    npx -y ccusage --json --start "$(date -u +%Y-%m-%d)" 2>/dev/null || echo '{}'
  else
    today="$(date -u +%Y-%m-%d)"
    # Approximate: bytes of all JSONL files (proxy, not authoritative).
    proj_dir="$HOME/.claude/projects"
    if [[ -d "$proj_dir" ]]; then
      total=$(find "$proj_dir" -name "*.jsonl" -newermt "$today" -exec wc -c {} + 2>/dev/null | tail -1 | awk '{print $1}')
      echo "{\"approx_bytes\": ${total:-0}}"
    else
      echo "{}"
    fi
  fi
}

run_one() {
  local label="$1"
  local delivery="$2"
  shift 2
  local extra_flags=("$@")

  step "Run: $label"
  echo "  Delivery: $delivery"
  echo "  Flags:    ${extra_flags[*]:-(none)}"

  # Snapshot ccusage BEFORE the run
  local before_file="${RESULT_FILE%.json}-${label}-before.json"
  ccusage_snapshot > "$before_file"
  ok "Pre-run ccusage snapshot: $before_file"

  # Initialize delivery scaffold (idempotent if exists)
  if [[ ! -d "$delivery" ]]; then
    zo init "$(basename "$delivery")" --no-tmux --scaffold-delivery "$delivery" \
      --branch main --no-detect 2>&1 | tail -5
  else
    echo "  (delivery exists — reusing)"
  fi

  # Capture run start time
  local start_ts="$(date -u +%s)"

  # Run zo build with --gate-mode full-auto so neither run waits on humans.
  # IMPORTANT: this needs to be run interactively in tmux to actually do work;
  # --no-tmux is single-shot only. Document this constraint:
  echo ""
  echo "  ⚠  zo build needs an interactive tmux session for multi-phase work."
  echo "     Run this command MANUALLY in a tmux session, then return here:"
  echo ""
  echo "      tmux new-session -d -s zo-bench-$label \\"
  echo "        \"zo build $PLAN_PATH --gate-mode full-auto ${extra_flags[*]:-}\""
  echo ""
  echo "  Press [Enter] when the build has completed (session ends with 'Session completed.')"
  read -r

  local end_ts="$(date -u +%s)"
  local wall_seconds=$((end_ts - start_ts))

  # Snapshot ccusage AFTER the run
  local after_file="${RESULT_FILE%.json}-${label}-after.json"
  ccusage_snapshot > "$after_file"
  ok "Post-run ccusage snapshot: $after_file"

  # Record run metadata
  local meta_file="${RESULT_FILE%.json}-${label}-meta.json"
  cat > "$meta_file" <<EOF
{
  "label": "$label",
  "delivery": "$delivery",
  "extra_flags": [$(printf '"%s",' "${extra_flags[@]}" | sed 's/,$//')],
  "start_ts": $start_ts,
  "end_ts": $end_ts,
  "wall_seconds": $wall_seconds,
  "wall_minutes": $(echo "scale=1; $wall_seconds/60" | bc -l 2>/dev/null || echo "$wall_seconds/60")
}
EOF
  ok "Metadata: $meta_file"
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if [[ "$RUN_DEFAULT" == "true" ]]; then
  run_one "default" "$DEFAULT_DELIVERY"
fi

if [[ "$RUN_LOW_TOKEN" == "true" ]]; then
  run_one "low-token" "$LOW_TOKEN_DELIVERY" --low-token
fi

# ---------------------------------------------------------------------------
# Summarise
# ---------------------------------------------------------------------------

step "Comparison"
echo ""
echo "Result files:"
ls -la "${RESULT_FILE%.json}"-*.json 2>/dev/null | awk '{print "  " $NF}'

# Build the final results file with whatever we have.
python3 <<PYTHON
import json
import os
import sys
from pathlib import Path

prefix = "${RESULT_FILE%.json}"
results = {
    "version": "1.0.2",
    "timestamp": "$TIMESTAMP",
    "plan": "$PLAN_PATH",
    "runs": {}
}

for label in ("default", "low-token"):
    meta_path = Path(f"{prefix}-{label}-meta.json")
    if not meta_path.exists():
        continue
    with open(meta_path) as f:
        meta = json.load(f)
    before_path = Path(f"{prefix}-{label}-before.json")
    after_path = Path(f"{prefix}-{label}-after.json")
    before = json.loads(before_path.read_text()) if before_path.exists() else {}
    after = json.loads(after_path.read_text()) if after_path.exists() else {}
    results["runs"][label] = {
        "meta": meta,
        "ccusage_before": before,
        "ccusage_after": after,
    }

with open("$RESULT_FILE", "w") as f:
    json.dump(results, f, indent=2)

print(f"\nFinal results: $RESULT_FILE")
print(f"\nRuns recorded: {list(results['runs'].keys())}")
for label, run in results["runs"].items():
    print(f"\n  {label}:")
    print(f"    wall time: {run['meta'].get('wall_minutes', 'n/a')} min")
PYTHON

echo ""
echo "Inspect the JSON files for full token breakdowns. To compute cost differences:"
echo "  jq '.runs[\"default\"], .runs[\"low-token\"]' $RESULT_FILE"
echo ""
echo "Update docs/reference/cost-benchmark.mdx with the measured numbers."
