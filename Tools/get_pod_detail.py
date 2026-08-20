import json

from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.parse_pod import _parse_pod
from utils.pod_resolver import resolve_pods


@mcp.tool(annotations={
    "title": "获取 Pod 详情",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def get_pod_detail(
    pod_name: str = "",
    namespace: str = "",
    label_selector: str = "",
    workload: str = "",
    workload_type: str = "",
    ctx: Context = None,
) -> str:
    """获取 Pod 的详细信息（类似 kubectl describe pod）。

    支持三种定位 Pod 的方式（优先级从高到低）：
    1. label_selector：按标签筛选 Pod，如 "app=flannel"
    2. workload + workload_type：按工作负载名查找关联 Pod，如 "my-app" + "Deployment"
    3. pod_name：Pod 名称（支持前缀匹配）

    匹配多个 Pod 时，返回 JSON 数组，每个元素对应一个 Pod。

    Args:
        pod_name: Pod 名称（精确或前缀匹配）
        namespace: 命名空间。workload 模式必填；其余模式可选用于缩小范围
        label_selector: 标签选择器，如 "app=flannel"
        workload: 工作负载名称
        workload_type: 工作负载类型，支持 Deployment/DaemonSet/StatefulSet，默认 Deployment
    """
    if not (pod_name or label_selector or workload):
        return "❌ 请提供 pod_name、label_selector 或 workload 其中之一"

    if workload and not namespace:
        return "❌ workload 模式下 namespace 必填"

    v1 = get_v1()

    try:
        pods = resolve_pods(
            v1, pod_name, namespace,
            label_selector, workload, workload_type
        )
    except ApiException as e:
        if e.status == 404:
            return f"❌ 资源不存在: {e.reason}"
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"
    except ValueError as e:
        return f"❌ {e}"

    if not pods:
        if label_selector:
            return f"❌ 未找到匹配标签 '{label_selector}' 的 Pod"
        if workload:
            return f"❌ 未找到 {workload_type or 'Deployment'} '{namespace}/{workload}' 关联的 Pod"
        return f"❌ 未找到匹配 Pod"

    await ctx.info(f"共匹配 {len(pods)} 个 Pod，正在获取详情...")

    details = []
    for ns, name, pod in pods:
        info = _parse_pod(pod)
        details.append(info)

    if len(details) == 1:
        return json.dumps(details[0], indent=2, ensure_ascii=False, default=str)
    return json.dumps(details, indent=2, ensure_ascii=False, default=str)
