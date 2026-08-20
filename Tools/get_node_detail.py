import json

from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.parse_node import _parse_node


@mcp.tool(annotations={
    "title": "获取节点详情",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def get_node_detail(
    node_name: str,
    ctx: Context = None,
) -> str:
    """获取指定节点的详细信息（类似 kubectl describe node）。

    返回节点的完整信息，包括：系统信息、资源容量、标签、污点、Conditions 等。

    Args:
        node_name: 节点名称，如 "node-01" 或 "ip-10-0-1-100"
    """
    v1 = get_v1()

    try:
        await ctx.info(f"正在查询节点 {node_name} 的详细信息...")
        node = v1.read_node(name=node_name)
    except ApiException as e:
        if e.status == 404:
            return f"❌ 节点 '{node_name}' 不存在，请检查节点名称"
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"

    info = _parse_node(node)

    return json.dumps(info, indent=2, ensure_ascii=False, default=str)
