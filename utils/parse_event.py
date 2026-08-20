"""K8s Event 解析：去重、排序、格式化。"""

from datetime import datetime, timezone
from typing import Tuple


def _get_event_time(e) -> datetime:
    """取 Event 的最新时间戳（last_timestamp 优先，回退 event_time）。

    返回带 tzinfo 的 datetime，无时间戳时返回 datetime.min(utc)，
    用于新旧比较。兼容 V1Event 对象和字典两种形态。
    """
    ts = None
    if hasattr(e, "last_timestamp"):
        ts = e.last_timestamp or getattr(e, "event_time", None)
    elif isinstance(e, dict):
        ts = e.get("lastTimestamp") or e.get("eventTime")

    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        from dateutil import parser as _dateutil_parser
        parsed = _dateutil_parser.parse(ts)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _event_key(e) -> Tuple:
    """构造 Event 去重 key：(namespace, kind, name, reason, message)。

    包含 namespace，避免跨命名空间同名资源被错误合并。
    """
    if hasattr(e, "involved_object"):
        inv = e.involved_object
        md = e.metadata
        kind = inv.kind if inv else ""
        name = inv.name if inv else ""
        ns = md.namespace if md else ""
        reason = e.reason or ""
        msg = e.message or ""
    else:
        inv = e.get("involvedObject", {}) or {}
        md = e.get("metadata", {}) or {}
        kind = inv.get("kind", "") if inv else ""
        name = inv.get("name", "") if inv else ""
        ns = md.get("namespace", "") if md else ""
        reason = e.get("reason", "") or ""
        msg = e.get("message", "") or ""

    return (ns, kind, name, reason, msg)


def _deduplicate_events(events) -> list:
    """按 (namespace, involved_object, reason, message) 去重，保留最新一条。

    K8s Events 在 List-Watch 过程中可能重复推送，同一资源的同一类告警
    合并为一条，按 last_timestamp/event_time 取最新。
    """
    seen: dict = {}  # key -> event 对象
    for e in events:
        key = _event_key(e)
        existing = seen.get(key)
        if existing is None:
            seen[key] = e
            continue
        if _get_event_time(e) >= _get_event_time(existing):
            seen[key] = e
    return list(seen.values())


def _sort_events_by_time(events) -> list:
    """按 last_timestamp 倒序排列（最新事件在前）。"""
    return sorted(events, key=_get_event_time, reverse=True)


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
    """格式化 Watch 事件（含 ADDED/MODIFIED/DELETED 标记）。

    兼容 V1Event 对象和字典两种形态。
    """
    watch_type = event.get("type", "???") if isinstance(event, dict) else "???"
    e = event.get("object") if isinstance(event, dict) else None

    if e is None:
        return f"  [{watch_type}] (空对象)"

    if hasattr(e, "involved_object"):
        # V1Event 对象
        inv = e.involved_object
        inv_str = f"{inv.kind}/{inv.name}" if inv else "N/A"
        md = e.metadata
        ns = md.namespace if md else ""
        reason = e.reason or ""
        msg = e.message or ""
        etype = e.type or ""
        ts = e.last_timestamp or getattr(e, "event_time", None)
    elif isinstance(e, dict):
        # 备用：字典形态
        inv = e.get("involvedObject", {}) or {}
        inv_str = f"{inv.get('kind','?')}/{inv.get('name','?')}" if inv else "N/A"
        md = e.get("metadata", {}) or {}
        ns = md.get("namespace", "") if md else ""
        reason = e.get("reason", "") or ""
        msg = e.get("message", "") or ""
        etype = e.get("type", "") or ""
        ts = e.get("lastTimestamp") or e.get("eventTime")
    else:
        return f"  [{watch_type}] 未知事件类型: {type(e).__name__}"

    action_map = {"ADDED": "🆕", "MODIFIED": "✏️", "DELETED": "🗑️"}
    icon = action_map.get(watch_type, f"[{watch_type}]")

    if ts and isinstance(ts, datetime):
        if ts.tzinfo:
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S %Z")
        else:
            ts_str = ts.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    elif ts:
        ts_str = str(ts)
    else:
        ts_str = "N/A"

    return (
        f"  {icon} {etype} | {reason} | {inv_str} ({ns})"
        f"\n    {msg}"
        f"\n    时间: {ts_str}"
    )
