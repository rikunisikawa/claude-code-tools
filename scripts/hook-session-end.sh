#!/usr/bin/env python3
# Stop hook: セッション終了時にサマリーをJSONLに追記する
# stdin: { "session_id", "transcript_path", "cwd", ... }

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
transcript_path = data.get("transcript_path", "")

tool_counts: dict = {}
if transcript_path and os.path.exists(transcript_path):
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                msg = item.get("message", {})
                if isinstance(msg, dict):
                    for block in msg.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            t = block.get("name", "unknown")
                            tool_counts[t] = tool_counts.get(t, 0) + 1
            except Exception:
                continue

record = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "session_id": session_id,
    "cwd": data.get("cwd", os.getcwd()),
    "total_tools": sum(tool_counts.values()),
    "tool_counts": tool_counts,
}

os.makedirs(os.path.dirname(log_file), exist_ok=True)
with open(log_file, "a") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
