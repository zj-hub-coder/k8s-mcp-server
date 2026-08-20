from datetime import datetime, timezone

from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1


def _calc_pod_age(creation_timestamp) -> str:
    """把创建时间格式化为可读的 age 字符串（类似 kubectl 的 AGE 列）。"""
    if creation_timestamp is None:
        return "Unknown"
    now = datetime.now(timezone.utc)
    delta = now - creation_timestamp
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"{days}d{hours}h"
    if hours > 0:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


def _safe_str(val, default="N/A") -> str:
    """None 转成默认占位符，其余直接转字符串，避免表格里出现空值。"""
    if val is None:
        return default
    return str(val)


@mcp.tool(annotations={
    "title": "列出 Pod 列表",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def list_pods(
    namespace: str = "",
    label_selector: str = "",
    field_selector: str = "",
    ctx: Context = None,
) -> str:
    """列出集群中的 Pod（类似 kubectl get pods -o wide）。

    支持按命名空间、标签、字段过滤。常用于定位特定组件的 Pod。

    Args:
        namespace: 命名空间。为空则查所有命名空间；指定如 "kube-system" 则只查该命名空间
        label_selector: 标签选择器，按标签过滤 Pod。如 "app=flannel"、"k8s-app=kube-dns"
        field_selector: 字段选择器，按属性过滤 Pod。如 "status.phase=Running"、"spec.nodeName=worker-01"
    """
    v1 = get_v1()

    kwargs = {}
    if label_selector:
        kwargs["label_selector"] = label_selector
    if field_selector:
        kwargs["field_selector"] = field_selector

    try:
        if namespace:
            await ctx.info(f"正在查询命名空间 '{namespace}' 下的 Pod...")
            pods = v1.list_namespaced_pod(namespace=namespace, **kwargs)
        else:
            await ctx.info("正在查询所有命名空间的 Pod...")
            pods = v1.list_pod_for_all_namespaces(**kwargs)
    except ApiException as e:
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"

    if not pods.items:
        return "未找到匹配的 Pod"

    await ctx.info(f"共找到 {len(pods.items)} 个 Pod，正在解析...")

    phase_counts = {}
    total_restarts = 0

    header = (
        f"{'NAMESPACE':<20} {'NAME':<45} {'READY':<8} {'STATUS':<18} "
        f"{'RESTARTS':<10} {'AGE':<8} {'IP':<16} {'NODE':<16}"
    )
    result_lines = [
        f"Pod 列表（共 {len(pods.items)} 个）",
        "=" * 140,
        header,
        "-" * 140,
    ]

    for pod in pods.items:
        metadata = pod.metadata
        status = pod.status
        spec = pod.spec

        ns = _safe_str(metadata.namespace, "")
        name = _safe_str(metadata.name, "")
        pod_ip = _safe_str(status.pod_ip if status else None, "N/A")
        node = _safe_str(spec.node_name if spec else None, "")

        phase = "Unknown"
        if status and status.phase:
            phase = status.phase
            if status.phase == "Pending":
                for cond in (status.conditions or []):
                    if cond.type == "PodScheduled" and cond.status == "False":
                        phase = f"Pending({_safe_str(cond.reason, 'NotScheduled')})"
                        break

        ready_count = 0
        total_containers = 0
        restarts = 0
        if status and status.container_statuses:
            for cs in status.container_statuses:
                total_containers += 1
                if cs.ready:
                    ready_count += 1
                restarts += (cs.restart_count or 0)

        ready_str = f"{ready_count}/{total_containers}" if total_containers > 0 else "0/0"
        total_restarts += restarts
        age = _calc_pod_age(metadata.creation_timestamp)

        result_lines.append(
            f"{ns:<20} "
            f"{name:<45} "
            f"{ready_str:<8} "
            f"{phase:<18} "
            f"{restarts:<10} "
            f"{age:<8} "
            f"{pod_ip:<16} "
            f"{node:<16}"
        )

        phase_key = phase.split("(")[0]
        phase_counts[phase_key] = phase_counts.get(phase_key, 0) + 1

    result_lines.append("-" * 140)
    summary_parts = [f"{k}={v}" for k, v in phase_counts.items()]
    result_lines.append(
        f"汇总: {', '.join(summary_parts)}, Total Restarts={total_restarts}, "
        f"Total={len(pods.items)}"
    )

    return "\n".join(result_lines)
