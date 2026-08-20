"""Node / Pod Watch 事件的状态变更检测与格式化。

记录上一次资源的关键状态快照，MODIFIED 事件到来时对比新旧快照，
只在状态发生质变（如 Ready→NotReady、CrashLoopBackOff）时输出告警。
"""

import json


# ==================== Node Watch ====================

def _node_snapshot(node) -> dict:
    """提取节点的关键状态快照，用于前后对比。"""
    status = node.status
    conditions = {}
    if status and status.conditions:
        for c in status.conditions:
            conditions[c.type] = c.status

    return {
        "name": node.metadata.name,
        "ready": conditions.get("Ready", "Unknown"),
        "memory_pressure": conditions.get("MemoryPressure", "Unknown"),
        "disk_pressure": conditions.get("DiskPressure", "Unknown"),
        "pid_pressure": conditions.get("PIDPressure", "Unknown"),
        "unschedulable": node.spec.unschedulable if node.spec else False,
    }


def _detect_node_change(old_snap, new_snap) -> list:
    """对比节点前后快照，返回有意义的变更列表。"""
    changes = []
    if old_snap is None:
        return changes

    field_labels = {
        "ready": ("Ready 状态", {"True": "✅ Ready", "False": "❌ NotReady", "Unknown": "❓ Unknown"}),
        "memory_pressure": ("内存压力", {"False": "✅ 无压力", "True": "⚠️ MemoryPressure"}),
        "disk_pressure": ("磁盘压力", {"False": "✅ 无压力", "True": "⚠️ DiskPressure"}),
        "pid_pressure": ("PID 压力", {"False": "✅ 无压力", "True": "⚠️ PIDPressure"}),
        "unschedulable": ("调度状态", {False: "✅ 可调度", True: "🚫 SchedulingDisabled"}),
    }

    for field, (label, mapping) in field_labels.items():
        old_val = old_snap.get(field)
        new_val = new_snap.get(field)
        if old_val != new_val:
            old_label = mapping.get(old_val, str(old_val))
            new_label = mapping.get(new_val, str(new_val))
            changes.append(f"  {label}: {old_label} → {new_label}")

    return changes


def format_node_watch(event_type, node, old_snap=None) -> str:
    """格式化 Node Watch 事件。"""
    node_name = node.metadata.name

    if event_type == "ADDED":
        snap = _node_snapshot(node)
        ready_icon = "✅" if snap["ready"] == "True" else "❌"
        return (
            f"🆕 节点新增: {node_name}\n"
            f"  状态: {ready_icon} {'Ready' if snap['ready'] == 'True' else 'NotReady'}\n"
            f"  内存: {'⚠️ MemoryPressure' if snap['memory_pressure'] == 'True' else '✅ OK'}\n"
            f"  磁盘: {'⚠️ DiskPressure' if snap['disk_pressure'] == 'True' else '✅ OK'}\n"
            f"  PID:  {'⚠️ PIDPressure' if snap['pid_pressure'] == 'True' else '✅ OK'}"
        )

    elif event_type == "MODIFIED":
        new_snap = _node_snapshot(node)
        changes = _detect_node_change(old_snap, new_snap)
        if not changes:
            return None  # 无实质变更，跳过
        return (
            f"✏️ 节点变更: {node_name}\n"
            + "\n".join(changes)
        )

    elif event_type == "DELETED":
        return f"🗑️ 节点删除: {node_name}"

    return f"[{event_type}] 节点: {node_name}"


# ==================== Pod Watch ====================

def _pod_snapshot(pod) -> dict:
    """提取 Pod 的关键状态快照，用于前后对比。"""
    metadata = pod.metadata
    spec = pod.spec
    status = pod.status

    snapshot = {
        "name": metadata.name,
        "namespace": metadata.namespace,
        "phase": status.phase if status else "Unknown",
        "node": spec.node_name if spec else "",
        "container_states": {},
        "restart_counts": {},
    }

    if status and status.container_statuses:
        for cs in status.container_statuses:
            state = "unknown"
            if cs.state.waiting:
                state = cs.state.waiting.reason or "Waiting"
            elif cs.state.terminated:
                state = cs.state.terminated.reason or "Terminated"
            elif cs.state.running:
                state = "Running"

            snapshot["container_states"][cs.name] = state
            snapshot["restart_counts"][cs.name] = cs.restart_count

    return snapshot


def _detect_pod_change(old_snap, new_snap) -> list:
    """对比 Pod 前后快照，返回有意义的变更列表。"""
    changes = []
    if old_snap is None:
        return changes

    # Phase 变更
    old_phase = old_snap.get("phase", "")
    new_phase = new_snap.get("phase", "")
    if old_phase != new_phase:
        changes.append(f"  Phase: {old_phase} → {new_phase}")

    # 节点变更
    old_node = old_snap.get("node", "")
    new_node = new_snap.get("node", "")
    if old_node != new_node:
        changes.append(f"  Node: {old_node or 'N/A'} → {new_node or 'N/A'}")

    # 容器状态变更
    old_states = old_snap.get("container_states", {})
    new_states = new_snap.get("container_states", {})
    all_containers = set(old_states.keys()) | set(new_states.keys())
    for cname in sorted(all_containers):
        old_state = old_states.get(cname, "N/A")
        new_state = new_states.get(cname, "N/A")
        if old_state != new_state:
            changes.append(f"  容器 {cname}: {old_state} → {new_state}")

    # 重启次数增加
    old_restarts = old_snap.get("restart_counts", {})
    new_restarts = new_snap.get("restart_counts", {})
    for cname in sorted(new_restarts.keys()):
        old_r = old_restarts.get(cname, 0)
        new_r = new_restarts.get(cname, 0)
        if new_r > old_r:
            changes.append(f"  容器 {cname} 重启: {old_r} → {new_r}")

    return changes


# 需要告警的 Pod 状态关键词
_POD_ALERT_STATES = {"CrashLoopBackOff", "ImagePullBackOff", "Error", "OOMKilled", "Pending"}


def format_pod_watch(event_type, pod, old_snap=None) -> str:
    """格式化 Pod Watch 事件。"""
    name = pod.metadata.name
    ns = pod.metadata.namespace

    if event_type == "ADDED":
        snap = _pod_snapshot(pod)
        phase = snap["phase"]
        is_alert = phase in _POD_ALERT_STATES
        icon = "🚨" if is_alert else "🆕"
        return (
            f"{icon} Pod 新增: {ns}/{name}\n"
            f"  Phase: {phase}\n"
            f"  Node: {snap['node'] or 'N/A'}\n"
            + _format_container_states(snap)
        )

    elif event_type == "MODIFIED":
        new_snap = _pod_snapshot(pod)
        changes = _detect_pod_change(old_snap, new_snap)
        if not changes:
            return None  # 无实质变更，跳过

        # 检查是否进入告警状态
        phase = new_snap["phase"]
        icon = "🚨" if phase in _POD_ALERT_STATES else "✏️"

        return (
            f"{icon} Pod 变更: {ns}/{name}\n"
            + "\n".join(changes)
        )

    elif event_type == "DELETED":
        return f"🗑️ Pod 删除: {ns}/{name}"

    return f"[{event_type}] Pod: {ns}/{name}"


def _format_container_states(snap) -> str:
    """格式化容器状态摘要。"""
    states = snap.get("container_states", {})
    restarts = snap.get("restart_counts", {})
    if not states:
        return "  容器: 未就绪"
    lines = []
    for cname, state in states.items():
        restart = restarts.get(cname, 0)
        alert = state in _POD_ALERT_STATES
        icon = "🚨" if alert else "  "
        lines.append(f"{icon} {cname}: {state} (restarts={restart})")
    return "\n".join(lines)
