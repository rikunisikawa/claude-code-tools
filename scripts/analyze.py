#!/usr/bin/env python3
"""
Claude Code 使用状況分析スクリプト
~/.claude/logs/ と ~/.claude/stats-cache.json, history.jsonl を読み込み、
日次レポートを生成する。
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
LOGS_DIR = CLAUDE_DIR / "logs"
REPORTS_DIR = LOGS_DIR / "reports"
TOOL_LOG = LOGS_DIR / "tool-usage.jsonl"
SESSION_LOG = LOGS_DIR / "session-summary.jsonl"
STATS_CACHE = CLAUDE_DIR / "stats-cache.json"
HISTORY = CLAUDE_DIR / "history.jsonl"


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def analyze_stats_cache(stats: dict) -> str:
    lines = ["## コスト・トークン分析\n"]

    daily = stats.get("dailyTokenUsage", {})
    if not daily:
        return "## コスト・トークン分析\n\nデータなし\n"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    week_input = week_output = week_cache_read = week_cache_create = 0
    recent_days = []

    for date_str, models in sorted(daily.items(), reverse=True)[:14]:
        day_input = day_output = day_cache_read = day_cache_create = 0
        for model, usage in models.items():
            day_input += usage.get("inputTokens", 0)
            day_output += usage.get("outputTokens", 0)
            day_cache_read += usage.get("cacheReadTokens", 0)
            day_cache_create += usage.get("cacheCreationTokens", 0)
        recent_days.append((date_str, day_input, day_output, day_cache_read, day_cache_create))
        if date_str >= week_ago:
            week_input += day_input
            week_output += day_output
            week_cache_read += day_cache_read
            week_cache_create += day_cache_create

    lines.append("### 直近7日間の合計\n")
    lines.append(f"- Input: {format_tokens(week_input)} tokens")
    lines.append(f"- Output: {format_tokens(week_output)} tokens")
    lines.append(f"- Cache read: {format_tokens(week_cache_read)} tokens")
    lines.append(f"- Cache create: {format_tokens(week_cache_create)} tokens\n")

    lines.append("### 日次内訳（直近7日）\n")
    lines.append("| 日付 | Input | Output | Cache Read |")
    lines.append("|------|-------|--------|------------|")
    for date_str, inp, out, cr, _ in recent_days[:7]:
        lines.append(f"| {date_str} | {format_tokens(inp)} | {format_tokens(out)} | {format_tokens(cr)} |")
    lines.append("")

    # モデル別使用状況
    model_usage: dict = defaultdict(lambda: defaultdict(int))
    for date_str, models in daily.items():
        if date_str >= week_ago:
            for model, usage in models.items():
                model_usage[model]["input"] += usage.get("inputTokens", 0)
                model_usage[model]["output"] += usage.get("outputTokens", 0)

    if model_usage:
        lines.append("### モデル別使用量（直近7日）\n")
        lines.append("| モデル | Input | Output |")
        lines.append("|--------|-------|--------|")
        for model, usage in sorted(model_usage.items(), key=lambda x: -x[1]["input"]):
            short_model = model.split("-")[2] if model.count("-") >= 2 else model
            lines.append(f"| {short_model} | {format_tokens(usage['input'])} | {format_tokens(usage['output'])} |")
        lines.append("")

    return "\n".join(lines)


def analyze_tools(tool_records: list, session_records: list) -> str:
    lines = ["## ツール使用分析\n"]

    if not tool_records:
        lines.append("ツールログなし（次回セッションから収集されます）\n")
        return "\n".join(lines)

    # 全期間
    all_tools = Counter(r["tool"] for r in tool_records if "tool" in r)

    # 直近7日
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent = [r for r in tool_records if r.get("ts", "") >= week_ago]
    recent_tools = Counter(r["tool"] for r in recent if "tool" in r)

    lines.append(f"### ツール使用ランキング TOP10（直近7日: {len(recent)}回）\n")
    lines.append("| ランク | ツール | 呼び出し数 |")
    lines.append("|--------|--------|-----------|")
    for i, (tool, count) in enumerate(recent_tools.most_common(10), 1):
        lines.append(f"| {i} | {tool} | {count} |")
    lines.append("")

    # プロジェクト別活動
    project_tools: dict = Counter(r.get("cwd", "unknown") for r in recent)
    if project_tools:
        lines.append("### プロジェクト別ツール呼び出し（直近7日）\n")
        for cwd, count in project_tools.most_common(5):
            proj = os.path.basename(cwd) or cwd
            lines.append(f"- `{proj}`: {count}回")
        lines.append("")

    # セッション統計
    if session_records:
        recent_sessions = [s for s in session_records if s.get("ts", "") >= week_ago]
        if recent_sessions:
            avg_tools = sum(s.get("total_tools", 0) for s in recent_sessions) / len(recent_sessions)
            lines.append(f"### セッション統計（直近7日）\n")
            lines.append(f"- セッション数: {len(recent_sessions)}")
            lines.append(f"- 平均ツール呼び出し/セッション: {avg_tools:.1f}")
            lines.append("")

    return "\n".join(lines)


def analyze_history(records: list) -> str:
    lines = ["## 入力履歴分析\n"]

    if not records:
        return "\n".join(lines) + "データなし\n"

    week_ago_ms = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000
    recent = [r for r in records if r.get("timestamp", 0) >= week_ago_ms]

    # プロジェクト別
    project_counts: Counter = Counter(r.get("project", "unknown") for r in recent)

    lines.append(f"### プロジェクト別プロンプト数（直近7日: {len(recent)}件）\n")
    for proj, count in project_counts.most_common(8):
        proj_name = os.path.basename(proj) or proj
        lines.append(f"- `{proj_name}`: {count}件")
    lines.append("")

    # 時間帯分析
    hour_counts: Counter = Counter()
    for r in recent:
        ts_ms = r.get("timestamp", 0)
        if ts_ms:
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            # JSTに変換 (UTC+9)
            jst_hour = (dt.hour + 9) % 24
            hour_counts[jst_hour] += 1

    if hour_counts:
        peak_hour = hour_counts.most_common(1)[0][0]
        lines.append(f"### 活動時間帯（JST）\n")
        lines.append(f"- ピーク時間帯: {peak_hour}時台")
        active_hours = sorted([h for h, c in hour_counts.most_common(5)])
        lines.append(f"- 上位5時間帯: {', '.join(f'{h}時' for h in active_hours)}")
        lines.append("")

    return "\n".join(lines)


def generate_optimization_suggestions(tool_records: list, stats: dict) -> str:
    lines = ["## 最適化提案\n"]
    suggestions = []

    # キャッシュ効率チェック
    daily = stats.get("dailyTokenUsage", {})
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    total_input = total_cache_read = 0
    for date_str, models in daily.items():
        if date_str >= week_ago:
            for model, usage in models.items():
                total_input += usage.get("inputTokens", 0)
                total_cache_read += usage.get("cacheReadTokens", 0)

    if total_input > 0:
        cache_rate = total_cache_read / (total_input + total_cache_read) * 100
        if cache_rate < 30:
            suggestions.append(
                f"- **キャッシュヒット率が低い** ({cache_rate:.1f}%): "
                "CLAUDE.mdに繰り返し参照するコンテキストを追加するとキャッシュ効率が上がります"
            )
        else:
            suggestions.append(f"- キャッシュヒット率: {cache_rate:.1f}% (良好)")

    # 頻出ツールのallowlist候補
    if tool_records:
        week_ago_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        recent = [r for r in tool_records if r.get("ts", "") >= week_ago_iso]
        bash_count = sum(1 for r in recent if r.get("tool") == "Bash")
        read_count = sum(1 for r in recent if r.get("tool") == "Read")

        if bash_count > 20:
            suggestions.append(
                f"- **Bashが{bash_count}回呼び出されています**: "
                "`/fewer-permission-prompts` スキルを実行してallowlistを自動更新することを推奨します"
            )
        if read_count > 30:
            suggestions.append(
                f"- **Readが{read_count}回呼び出されています**: "
                "Readは通常自動許可されていますが、設定を確認してください"
            )

    if not suggestions:
        suggestions.append("- 現時点で特筆すべき最適化ポイントはありません")

    lines.extend(suggestions)
    lines.append("")
    lines.append("### 手動最適化コマンド\n")
    lines.append("```bash")
    lines.append("# allowlistの自動更新")
    lines.append("# Claude Codeで: /fewer-permission-prompts")
    lines.append("")
    lines.append("# 古いメモリファイルの確認")
    lines.append("find ~/.claude/projects -name '*.md' -mtime +30 -ls")
    lines.append("")
    lines.append("# ログサイズ確認")
    lines.append("du -sh ~/.claude/logs/")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{today}.md"

    # データ読み込み
    tool_records = read_jsonl(TOOL_LOG)
    session_records = read_jsonl(SESSION_LOG)
    stats = read_json(STATS_CACHE)
    history_records = read_jsonl(HISTORY)

    # レポート生成
    sections = [
        f"# Claude Code 使用状況レポート ({today})\n",
        f"生成時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
        "---\n",
        analyze_stats_cache(stats),
        analyze_tools(tool_records, session_records),
        analyze_history(history_records),
        generate_optimization_suggestions(tool_records, stats),
    ]

    report = "\n".join(sections)

    with open(report_path, "w") as f:
        f.write(report)

    print(f"レポートを生成しました: {report_path}")
    print(report)
    return str(report_path)


if __name__ == "__main__":
    main()
