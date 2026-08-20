"""K8s Event 解析：去重、排序、格式化。"""

from datetime import datetime, timezone
from typing import List, Tuple


def _deduplicate_events(events) -> list:
    """按 (involved_object, reason, message) 去重，保留最新一条。

    K8s Events 在 List-Watch 过程中可能产生重复，
    同一资源的同一类告警应合并为一条，取最新时间戳。
    """
    seen: dict[Tuple, int] = {}
    result = []
    for i, e in enumerate(events):
        key = (
            (e.involved_object.kind if e.involved_object else ""),
            (e.involved_object.name if e.involved_object else ""),
            e.reason or "",
            e.message or "",
        )
        if key in seen:
            # 已存在同 key，用后者覆盖前者
            result[seen[key]] = None
        seen[key] = i
        result.append(e)
    return [e for e in result if e is not None]


def _sort_events_by_time(events) -> list:
    """按 last_timestamp 倒序排列（最新事件在前）。"""
    def _ts(e):
        ts = e.last_timestamp or e.event_time
        if ts is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if isinstance(ts, datetime):
            return ts
        return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts

    return sorted(events, key=_ts, reverse=True)


def _format_event(e) -> str:
    """格式化单条 Event 为可读字符串。"""
    inv = e.involved_object
    inv_str = f"{inv.kind}/{inv.name}" if inv else "N/A"

    ts = e.last_timestamp or e.event_time
    if ts and isinstance(ts, datetime):
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S %Z")
    elif ts:
        ts_str = str(ts)
    else:
        ts_str = "N/A"

    return (
        f"  [{e.type or 'Normal'}] {e.reason or 'N/A'} | {inv_str} ({e.metadata.namespace})"
        f"\n    {e.message or ''}"
        f"\n    时间: {ts_str}"
    )


def _format_event_watch(event) -> str:
    """格式化 Watch 事件（含 ADDED/MODIFIED/DELETED 标记）。"""
    watch_type = event.get("type", "???")
    e = event.get("object", {})
    inv = e.get("involvedObject", {})
    inv_str = f"{inv.get('kind','?')}/{inv.get('name','?')}" if inv else "N/A"
    ns = e.get("metadata", {}).get("namespace", "")
    reason = e.get("reason", "")
    msg = e.get("message", "")
    etype = e.get("type", "")
    ts = e.get("lastTimestamp", "")

    action_map = {"ADDED": "🆕", "MODIFIED": "✏️", "DELETED": "🗑️"}
    icon = action_map.get(watch_type, f"[{watch_type}]")

    return (
        f"  {icon} {etype} | {reason} | {inv_str} ({ns})"
        f"\n    {msg}"
        f"\n    时间: {ts}"
    )
