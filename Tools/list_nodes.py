from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.parse_node import _parse_node


@mcp.tool(annotations={
    "title": "列出集群节点",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def list_nodes(
    label_selector: str = "",
    ctx: Context = None,
) -> str:
    """列出 K8s 集群中所有节点的概览信息（类似 kubectl get nodes -o wide）。

    Args:
        label_selector: 标签选择器，用于过滤节点。
                        示例: "node-role.kubernetes.io/worker="
                        示例: "kubernetes.io/os=linux"
                        为空则返回所有节点。
    """
    v1 = get_v1()

    try:
        if label_selector:
            await ctx.info(f"正在查询节点 (label_selector={label_selector})...")
            nodes = v1.list_node(label_selector=label_selector)
        else:
            await ctx.info("正在查询所有节点...")
            nodes = v1.list_node()
    except ApiException as e:
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"

    if not nodes.items:
        return "未找到匹配的节点"

    await ctx.info(f"共找到 {len(nodes.items)} 个节点，正在解析...")

    # 构造类似 kubectl get nodes -o wide 的表格输出
    result_lines = [
        f"集群节点列表（共 {len(nodes.items)} 个）",
        "=" * 90,
        f"{'NAME':<30} {'STATUS':<20} {'ROLES':<15} {'AGE':<8} {'VERSION':<15} {'INTERNAL-IP':<16}",
        "-" * 90,
    ]

    for node in nodes.items:
        info = _parse_node(node)
        result_lines.append(
            f"{info['name']:<30} "
            f"{info['status']:<20} "
            f"{','.join(info['roles']):<15} "
            f"{info['age']:<8} "
            f"{info['version']:<15} "
            f"{info['internal_ip']:<16}"
        )

    # 汇总统计
    all_info = [_parse_node(n) for n in nodes.items]
    ready_count = sum(1 for n in all_info if n["status"] == "Ready")
    not_ready_count = sum(1 for n in all_info if n["status"] == "NotReady")
    disabled_count = sum(1 for n in all_info if n["status"] == "SchedulingDisabled")

    result_lines.append("-" * 90)
    result_lines.append(
        f"汇总: Ready={ready_count}, NotReady={not_ready_count}, "
        f"SchedulingDisabled={disabled_count}, Total={len(nodes.items)}"
    )

    return "\n".join(result_lines)
