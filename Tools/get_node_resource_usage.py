import json

from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.parse_resource import _parse_cpu, _parse_memory, _assess_node_resource


@mcp.tool(annotations={
    "title": "查询节点资源使用",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def get_node_resource_usage(
    node_name: str,
    ctx: Context = None,
) -> str:
    """查询指定节点上所有 Pod 的资源请求/限制汇总，评估节点资源使用情况。

    帮助判断节点是否存在资源过载风险。类似 kubectl describe node 中的 "Allocated resources" 部分。

    Args:
        node_name: 节点名称
    """
    v1 = get_v1()

    # 先验证节点是否存在
    try:
        node = v1.read_node(name=node_name)
    except ApiException as e:
        if e.status == 404:
            return f"❌ 节点 '{node_name}' 不存在"
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"

    # 获取该节点上所有 Pod
    await ctx.info(f"正在查询节点 {node_name} 上的 Pod 资源分配...")
    try:
        pods = v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={node_name},status.phase=Running"
        )
    except ApiException as e:
        return f"❌ 查询 Pod 失败: {e.status} - {e.reason}"

    # 汇总资源请求和限制
    total_cpu_requests = 0     # 单位: millicores
    total_cpu_limits = 0
    total_mem_requests = 0     # 单位: bytes
    total_mem_limits = 0
    pod_count = len(pods.items)

    for pod in pods.items:
        for container in (pod.spec.containers or []):
            resources = container.resources
            if resources:
                if resources.requests:
                    total_cpu_requests += _parse_cpu(resources.requests.get("cpu", "0"))
                    total_mem_requests += _parse_memory(resources.requests.get("memory", "0"))
                if resources.limits:
                    total_cpu_limits += _parse_cpu(resources.limits.get("cpu", "0"))
                    total_mem_limits += _parse_memory(resources.limits.get("memory", "0"))

    # 节点可分配资源
    allocatable = node.status.allocatable or {}
    alloc_cpu = _parse_cpu(allocatable.get("cpu", "0"))
    alloc_mem = _parse_memory(allocatable.get("memory", "0"))

    # 计算使用率百分比
    cpu_req_pct = (total_cpu_requests / alloc_cpu * 100) if alloc_cpu > 0 else 0
    cpu_lim_pct = (total_cpu_limits / alloc_cpu * 100) if alloc_cpu > 0 else 0
    mem_req_pct = (total_mem_requests / alloc_mem * 100) if alloc_mem > 0 else 0
    mem_lim_pct = (total_mem_limits / alloc_mem * 100) if alloc_mem > 0 else 0

    result = {
        "node_name": node_name,
        "running_pods": pod_count,
        "allocatable": {
            "cpu": f"{alloc_cpu}m",
            "memory": f"{alloc_mem // (1024**2)}Mi",
        },
        "resource_requests": {
            "cpu": f"{total_cpu_requests}m ({cpu_req_pct:.1f}%)",
            "memory": f"{total_mem_requests // (1024**2)}Mi ({mem_req_pct:.1f}%)",
        },
        "resource_limits": {
            "cpu": f"{total_cpu_limits}m ({cpu_lim_pct:.1f}%)",
            "memory": f"{total_mem_limits // (1024**2)}Mi ({mem_lim_pct:.1f}%)",
        },
        "assessment": _assess_node_resource(cpu_req_pct, mem_req_pct),
    }

    return json.dumps(result, indent=2, ensure_ascii=False)
