from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.watch_helper import run_watch_loop
from utils.parse_event import _format_event_watch


def _process_event(event, _state):
    """处理单条 Event Watch 事件。"""
    return _format_event_watch(event)


@mcp.tool(annotations={
    "title": "实时监听 K8s 事件",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def watch_events(
    namespace: str = "",
    filter_warning: bool = True,
    timeout_seconds: int = 30,
    max_events: int = 100,
    ctx: Context = None,
) -> str:
    """实时监听 K8s 事件流（基于 Watch API，类似 kubectl get events --watch）。

    在超时时间内持续监听，捕捉 Warning 事件。

    Args:
        namespace: 命名空间，留空表示所有命名空间
        filter_warning: 是否只监听 Warning 类型事件（默认 True）
        timeout_seconds: 监听超时秒数，默认 30，最小 5
        max_events: 最多收集的事件数，达到后提前退出
    """
    v1 = get_v1()

    field_parts = []
    if filter_warning:
        field_parts.append("type=Warning")
    field_selector = ",".join(field_parts) if field_parts else ""

    await ctx.info(
        f"开始监听事件 | 命名空间: {namespace or 'all'} | "
        f"仅 Warning: {filter_warning} | 超时: {timeout_seconds}s"
    )

    if namespace:
        list_fn = v1.list_namespaced_event

        def list_kwargs_fn(resource_version, iter_timeout):
            kwargs = {
                "namespace": namespace,
                "timeout_seconds": iter_timeout,
            }
            if resource_version:
                kwargs["resource_version"] = resource_version
            if field_selector:
                kwargs["field_selector"] = field_selector
            return kwargs
    else:
        list_fn = v1.list_event_for_all_namespaces

        def list_kwargs_fn(resource_version, iter_timeout):
            kwargs = {"timeout_seconds": iter_timeout}
            if resource_version:
                kwargs["resource_version"] = resource_version
            if field_selector:
                kwargs["field_selector"] = field_selector
            return kwargs

    collected, elapsed, error = await run_watch_loop(
        list_fn=list_fn,
        list_kwargs_fn=list_kwargs_fn,
        process_event_fn=_process_event,
        ctx=ctx,
        timeout_seconds=timeout_seconds,
        max_events=max_events,
    )

    if error:
        return error

    if not collected:
        return (
            f"监听 {elapsed:.1f}s，未捕获到 Warning 事件\n"
            f"（命名空间: {namespace or 'all'}，仅 Warning: {filter_warning}）"
        )

    lines = [
        f"实时事件监听结果（{elapsed:.1f}s，共 {len(collected)} 条）",
        "=" * 80,
    ]

    for item in collected:
        lines.append(item)
        lines.append("-" * 40)

    return "\n".join(lines)
