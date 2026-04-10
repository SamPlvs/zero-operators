#!/bin/bash -l
PROMPT=$(cat /Users/samtukra/Documents/code/personal/zero-operators/.claude/worktrees/blissful-babbage/logs/wrapper/zo-mnist-digit-classifier-prompt.txt)
/Users/samtukra/.local/bin/claude --model opus --max-turns 200 --add-dir /Users/samtukra/Documents/code/personal/zero-operators/.claude/worktrees/blissful-babbage --dangerously-skip-permissions -p "$PROMPT"
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
  echo ""
  echo "[ZO] Claude exited with code $EXIT_CODE"
  echo "[ZO] Press Enter to close this window..."
  read
fi
