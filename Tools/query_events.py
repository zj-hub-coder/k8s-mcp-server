from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.parse_event import _deduplicate_events, _sort_events_by_time, _format_event


@mcp.tool(annotations={
    "title": "查询 K8s 事件",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def query_events(
    namespace: str = "",
    resource_kind: str = "",
    resource_name: str = "",
    warning_only: bool = True,
    max_count: int = 50,
    ctx: Context = None,
) -> str:
    """查询 K8s 集群事件（类似 kubectl get events）。

    按时间倒序返回，自动去重（同一资源的同类告警合并为最新一条）。
    支持按命名空间 / 资源类型 / 资源名称筛选。

    Args:
        namespace: 命名空间，留空表示所有命名空间
        resource_kind: 资源类型过滤，如 "Pod"、"Node"、"Deployment"
        resource_name: 资源名称过滤，如 "my-app-pod-abcde"
        warning_only: 是否只返回 Warning 类型事件（默认 True，聚焦异常）
        max_count: 最多返回的事件数，默认 50
    """
    v1 = get_v1()

    field_parts = []
    if warning_only:
        field_parts.append("type=Warning")
    field_selector = ",".join(field_parts) if field_parts else ""

    try:
        if namespace:
            await ctx.info(f"正在查询命名空间 '{namespace}' 的事件...")
            events = v1.list_namespaced_event(
                namespace=namespace, field_selector=field_selector
            )
        else:
            await ctx.info("正在查询全命名空间事件...")
            events = v1.list_event_for_all_namespaces(
                field_selector=field_selector
            )
    except ApiException as e:
        return f"❌ K8s API 调用失败: {e.status} - {e.reason}"

    if not events.items:
        return "未找到事件"

    await ctx.info(f"共获取 {len(events.items)} 条事件，正在去重 + 排序...")

    # 筛选：资源类型 + 资源名称
    filtered = events.items
    if resource_kind:
        filtered = [
            e for e in filtered
            if e.involved_object and e.involved_object.kind == resource_kind
        ]
    if resource_name:
        filtered = [
            e for e in filtered
            if e.involved_object and e.involved_object.name == resource_name
        ]

    # 去重 + 排序
    deduped = _deduplicate_events(filtered)
    sorted_events = _sort_events_by_time(deduped)

    # 截取最近 max_count 条
    results = sorted_events[:max_count]

    # 汇总统计
    warning_count = sum(1 for e in results if e.type == "Warning")
    normal_count = len(results) - warning_count

    lines = [
        f"K8s 事件列表（共 {len(results)} 条，Warning={warning_count}, Normal={normal_count}）",
        "=" * 80,
    ]

    for e in results:
        lines.append(_format_event(e))
        lines.append("-" * 40)

    if not results:
        lines.append("无匹配事件")

    return "\n".join(lines)
