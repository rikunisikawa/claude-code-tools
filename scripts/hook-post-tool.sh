#!/usr/bin/env python3
# PostToolUse hook: ツール使用ログをJSONLに追記する
# stdinからJSON: { "tool_name", "tool_input", "tool_response", "session_id" }

import json
import os
import sys
from datetime import datetime, timezone

log_file = os.path.expanduser("~/.claude/logs/tool-usage.jsonl")

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
if not tool_name:
    sys.exit(0)

record = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "tool": tool_name,
    "session_id": data.get("session_id", ""),
    "cwd": os.getcwd(),
}

os.makedirs(os.path.dirname(log_file), exist_ok=True)
with open(log_file, "a") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
