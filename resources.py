"""MCP Resource 集合：以资源 URI 形式暴露可被 LLM 引用的只读快照。"""

import json

from app import mcp
from k8s_client import get_v1


@mcp.resource("k8s://cluster/summary")
def get_cluster_summary() -> str:
    """返回 K8s 集群的节点概览摘要"""
    try:
        v1 = get_v1()
        nodes = v1.list_node()
        node_count = len(nodes.items)
        ready = sum(
            1 for n in nodes.items
            if any(
                c.type == "Ready" and c.status == "True"
                for c in (n.status.conditions or [])
            )
        )
        versions = set(
            n.status.node_info.kubelet_version
            for n in nodes.items
            if n.status.node_info
        )
        return json.dumps({
            "total_nodes": node_count,
            "ready_nodes": ready,
            "not_ready_nodes": node_count - ready,
            "k8s_versions": sorted(versions),
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
