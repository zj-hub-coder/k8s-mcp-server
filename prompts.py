"""MCP Prompt 集合：给 LLM 提供运维引导。"""

from app import mcp


@mcp.prompt()
def node_troubleshoot(node_name: str) -> str:
    """K8s 节点故障排查引导"""
    return f"""你是一位资深 K8s 运维工程师。请对节点 {node_name} 进行系统排查：

1. 先使用 get_node_detail 获取节点详细信息
2. 检查节点 Conditions（Ready/MemoryPressure/DiskPressure/PIDPressure）
3. 使用 get_node_resource_usage 检查资源分配是否过载
4. 检查 Taints 是否导致了 Pod 调度异常
5. 根据以上信息给出诊断结论和修复建议

请逐步执行，并给出清晰的分析结论。"""


@mcp.prompt()
def cluster_health_check() -> str:
    """集群健康巡检引导"""
    return """你是一位 K8s 集群管理员，请执行每日健康巡检：

1. 使用 find_problem_nodes 扫描问题节点
2. 使用 list_nodes 查看所有节点概览
3. 对资源使用率最高的节点执行 get_node_resource_usage
4. 汇总巡检结果，按严重程度排列问题

请生成一份结构化的巡检报告。"""
