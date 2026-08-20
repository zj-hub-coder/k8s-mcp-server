"""节点对象解析：从 V1Node 提取结构化概要信息。"""

from datetime import datetime, timezone


def _format_age(creation_timestamp) -> str:
    """将创建时间格式化为可读的 age 字符串（类似 kubectl 的 AGE 列）"""
    if creation_timestamp is None:
        return "Unknown"
    now = datetime.now(timezone.utc)
    delta = now - creation_timestamp
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60
    if days > 0:
        return f"{days}d{hours}h"
    elif hours > 0:
        return f"{hours}h{minutes}m"
    else:
        return f"{minutes}m"


def _get_node_roles(labels: dict) -> list[str]:
    """从标签中提取节点角色（如 master, worker, etcd）"""
    roles = []
    for key in labels:
        if key.startswith("node-role.kubernetes.io/"):
            role = key.split("/", 1)[1]
            if role:
                roles.append(role)
    return roles or ["<none>"]


def _get_address(addresses, addr_type: str) -> str:
    """从地址列表中获取指定类型的地址"""
    if not addresses:
        return "N/A"
    for addr in addresses:
        if addr.type == addr_type:
            return addr.address
    return "N/A"


def _parse_node(node) -> dict:
    """从 V1Node 对象中提取关键信息，返回结构化字典"""
    status = node.status
    spec = node.spec
    metadata = node.metadata

    # 解析 Conditions（Ready / MemoryPressure / DiskPressure 等）
    conditions = {}
    if status.conditions:
        for c in status.conditions:
            conditions[c.type] = {
                "status": c.status,
                "message": c.message or "",
                "last_transition": str(c.last_transition_time or ""),
            }

    # 判断节点是否 Ready
    ready_condition = conditions.get("Ready", {})
    is_ready = ready_condition.get("status") == "True"

    # 判断是否被设置了 SchedulingDisabled（cordon）
    unschedulable = spec.unschedulable or False

    # 综合状态
    if unschedulable:
        node_status = "SchedulingDisabled"
    elif is_ready:
        node_status = "Ready"
    else:
        node_status = "NotReady"

    # 提取资源容量和可分配资源
    capacity = status.capacity or {}
    allocatable = status.allocatable or {}

    # 提取节点标签中的关键信息
    labels = metadata.labels or {}
    node_info = status.node_info

    return {
        "name": metadata.name,
        "status": node_status,
        "roles": _get_node_roles(labels),
        "age": _format_age(metadata.creation_timestamp),
        "version": node_info.kubelet_version if node_info else "Unknown",
        "os": f"{node_info.os_image}" if node_info else "Unknown",
        "arch": node_info.architecture if node_info else "Unknown",
        "kernel": node_info.kernel_version if node_info else "Unknown",
        "container_runtime": node_info.container_runtime_version if node_info else "Unknown",
        "internal_ip": _get_address(status.addresses, "InternalIP"),
        "hostname": _get_address(status.addresses, "Hostname"),
        "capacity": {
            "cpu": capacity.get("cpu", "N/A"),
            "memory": capacity.get("memory", "N/A"),
            "pods": capacity.get("pods", "N/A"),
            "ephemeral_storage": capacity.get("ephemeral-storage", "N/A"),
        },
        "allocatable": {
            "cpu": allocatable.get("cpu", "N/A"),
            "memory": allocatable.get("memory", "N/A"),
            "pods": allocatable.get("pods", "N/A"),
        },
        "conditions": conditions,
        "labels": {
            k: v for k, v in labels.items()
            if not k.startswith("node.kubernetes.io/")  # 过滤冗余标签
        },
        "taints": [
            {"key": t.key, "value": t.value or "", "effect": t.effect}
            for t in (spec.taints or [])
        ],
        "unschedulable": unschedulable,
    }
