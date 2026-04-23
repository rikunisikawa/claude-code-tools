#!/usr/bin/env python3
# Stop hook: セッション終了時にサマリーをJSONLに追記する
# stdinからJSON: { "session_id", "transcript", ... }

import json
import os
import sys
from datetime import datetime, timezone

log_file = os.path.expanduser("~/.claude/logs/session-summary.jsonl")

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

session_id = data.get("session_id", "")
transcript = data.get("transcript", [])

tool_counts: dict = {}
for item in transcript:
    if isinstance(item, dict) and item.get("type") == "tool_use":
        t = item.get("name", "unknown")
        tool_counts[t] = tool_counts.get(t, 0) + 1

record = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "session_id": session_id,
    "cwd": os.getcwd(),
    "total_tools": sum(tool_counts.values()),
    "tool_counts": tool_counts,
}

os.makedirs(os.path.dirname(log_file), exist_ok=True)
with open(log_file, "a") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
