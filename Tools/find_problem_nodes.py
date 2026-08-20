from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.parse_node import _parse_node


@mcp.tool(annotations={
    "title": "扫描问题节点",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def find_problem_nodes(ctx: Context = None) -> str:
    """扫描集群中存在问题的节点。

    检查以下问题: NotReady、SchedulingDisabled、MemoryPressure、DiskPressure、PIDPressure。
    用于快速发现集群中需要关注的节点。
    """
    v1 = get_v1()

    try:
        await ctx.info("正在扫描集群节点健康状态...")
        nodes = v1.list_node()
    except ApiException as e:
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"

    problems = []
    for node in nodes.items:
        info = _parse_node(node)
        issues = []

        # 检查 Ready 状态
        if info["status"] != "Ready":
            issues.append(f"状态: {info['status']}")

        # 检查各项 Conditions
        for cond_name in ["MemoryPressure", "DiskPressure", "PIDPressure"]:
            cond = info["conditions"].get(cond_name, {})
            if cond.get("status") == "True":
                issues.append(f"{cond_name}: {cond.get('message', 'True')}")

        if issues:
            problems.append({
                "node": info["name"],
                "ip": info["internal_ip"],
                "issues": issues,
            })

    if not problems:
        return f"✅ 集群所有 {len(nodes.items)} 个节点状态正常，未发现问题"

    result_lines = [f"⚠️ 发现 {len(problems)} 个问题节点（共 {len(nodes.items)} 个）：", ""]
    for p in problems:
        result_lines.append(f"  节点: {p['node']} ({p['ip']})")
        for issue in p["issues"]:
            result_lines.append(f"    - {issue}")
        result_lines.append("")

    return "\n".join(result_lines)
