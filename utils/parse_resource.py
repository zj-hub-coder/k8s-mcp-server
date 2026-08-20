"""资源解析：CPU/内存字符串量化与节点资源风险评估。"""


def _parse_cpu(cpu_str: str) -> int:
    """将 CPU 资源字符串解析为 millicores (如 '500m' -> 500, '2' -> 2000)"""
    if not cpu_str or cpu_str == "0":
        return 0
    cpu_str = str(cpu_str)
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    elif cpu_str.endswith("n"):
        return int(cpu_str[:-1]) // 1_000_000
    else:
        return int(float(cpu_str) * 1000)


def _parse_memory(mem_str: str) -> int:
    """将内存资源字符串解析为 bytes (如 '1Gi' -> 1073741824)"""
    if not mem_str or mem_str == "0":
        return 0
    mem_str = str(mem_str)
    units = {
        "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4,
        "K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4,
    }
    for suffix, multiplier in units.items():
        if mem_str.endswith(suffix):
            return int(float(mem_str[: -len(suffix)]) * multiplier)
    return int(mem_str)


def _assess_node_resource(cpu_pct: float, mem_pct: float) -> str:
    """根据 CPU 和内存请求占比评估节点状态"""
    issues = []
    if cpu_pct > 90:
        issues.append(f"CPU 请求占比 {cpu_pct:.1f}%，已严重过载")
    elif cpu_pct > 70:
        issues.append(f"CPU 请求占比 {cpu_pct:.1f}%，使用率偏高")

    if mem_pct > 90:
        issues.append(f"内存请求占比 {mem_pct:.1f}%，已严重过载")
    elif mem_pct > 70:
        issues.append(f"内存请求占比 {mem_pct:.1f}%，使用率偏高")

    if not issues:
        return "✅ 节点资源分配正常"
    return "⚠️ " + "; ".join(issues)
