#!/usr/bin/env bash
# optimize.sh: analyze.py の出力を元に settings.json のallowlistを提案・更新する

set -euo pipefail

SETTINGS="${HOME}/.claude/settings.json"
TOOL_LOG="${HOME}/.claude/logs/tool-usage.jsonl"

echo "=== Claude Code 最適化スクリプト ==="

# Pythonで頻出Bashコマンドを分析してallowlist候補を出力
python3 - <<'PYEOF'
import json
import os
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

tool_log = Path.home() / ".claude/logs/tool-usage.jsonl"
settings_file = Path.home() / ".claude/settings.json"

# ツールログ読み込み
records = []
if tool_log.exists():
    with open(tool_log) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

# settings.json 読み込み
settings = {}
if settings_file.exists():
    with open(settings_file) as f:
        try:
            settings = json.load(f)
        except Exception:
            pass

# 直近7日のツール使用集計
week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
recent = [r for r in records if r.get("ts", "") >= week_ago]
tool_counts = Counter(r["tool"] for r in recent if "tool" in r)

print("\n### 直近7日間のツール呼び出し回数")
for tool, count in tool_counts.most_common(15):
    print(f"  {tool}: {count}回")

# allowlist現状確認
current_allow = settings.get("permissions", {}).get("allow", [])
print(f"\n### 現在のallowlist ({len(current_allow)}件)")
for item in current_allow:
    print(f"  - {item}")

# 最適化ポイント
print("\n### 推奨アクション")
if tool_counts.get("Bash", 0) > 10:
    print("  → Claude Codeで /fewer-permission-prompts を実行してallowlistを自動更新")
if not any(a.startswith("Read") for a in current_allow):
    print("  → Readツールはデフォルト許可のため追加不要")

# ログサイズ確認
logs_dir = Path.home() / ".claude/logs"
total_size = sum(f.stat().st_size for f in logs_dir.rglob("*") if f.is_file())
print(f"\n### ログサイズ: {total_size / 1024:.1f} KB")
if total_size > 10 * 1024 * 1024:  # 10MB超
    print("  → ログが大きくなっています。古いエントリの削除を検討してください")
    print(f"    コマンド: tail -n 10000 ~/.claude/logs/tool-usage.jsonl > /tmp/tool-usage-trimmed.jsonl")

print("\n✓ 最適化チェック完了")
PYEOF
