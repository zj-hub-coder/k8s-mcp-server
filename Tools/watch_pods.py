from fastmcp import Context

from app import mcp
from k8s_client import get_v1
from utils.watch_helper import run_watch_loop
from utils.parse_watch import (
    _pod_snapshot,
    format_pod_watch,
)

# 记录 Pod 上一次的状态快照，用于变更对比
_pod_snapshots = {}


def _process_pod_event(event, _state):
    """处理单条 Pod Watch 事件。"""
    event_type = event.get("type", "???")
    obj = event.get("object", {})

    if isinstance(obj, dict):
        return None

    pod = obj
    ns = pod.metadata.namespace
    name = pod.metadata.name
    key = f"{ns}/{name}"

    old_snap = _pod_snapshots.get(key)
    formatted = format_pod_watch(event_type, pod, old_snap)

    # 更新快照
    if event_type in ("ADDED", "MODIFIED"):
        _pod_snapshots[key] = _pod_snapshot(pod)
    elif event_type == "DELETED" and key in _pod_snapshots:
        del _pod_snapshots[key]

    return formatted


@mcp.tool(annotations={
    "title": "实时监听 Pod 变化",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def watch_pods(
    namespace: str = "",
    label_selector: str = "",
    watch_all_namespaces: bool = True,
    timeout_seconds: int = 30,
    max_events: int = 100,
    ctx: Context = None,
) -> str:
    """实时监听 K8s Pod 状态变化（类似 kubectl get pods --watch）。

    捕捉 Pod Phase 变化（Pending/Running/Failed）、容器状态变化
    （CrashLoopBackOff/ImagePullBackOff/OOMKilled）、重启次数增加等，
    只在有实质变更时输出。

    Args:
        namespace: 命名空间，指定后只监听该命名空间的 Pod
        label_selector: 标签选择器，过滤 Pod
        watch_all_namespaces: 是否监听全部命名空间（默认 True）
        timeout_seconds: 监听超时秒数，默认 30，最小 5
        max_events: 最多收集的事件数，达到后提前退出
    """
    v1 = get_v1()

    # 预热：先拉一次当前 Pod 状态作为变更对比基线
    try:
        if namespace:
            pods = v1.list_namespaced_pod(namespace=namespace)
        else:
            pods = v1.list_pod_for_all_namespaces()
        for pod in pods.items:
            key = f"{pod.metadata.namespace}/{pod.metadata.name}"
            _pod_snapshots[key] = _pod_snapshot(pod)
        await ctx.info(f"基线加载完成：{len(_pod_snapshots)} 个 Pod")
    except Exception as e:
        await ctx.info(f"⚠️ 基线加载失败（非致命）：{str(e)[:100]}")

    scope = namespace or ("all namespaces" if watch_all_namespaces else "")
    await ctx.info(
        f"开始监听 Pod | 范围: {scope} | "
        f"label_selector: {label_selector or 'all'} | 超时: {timeout_seconds}s"
    )

    def list_kwargs_fn(resource_version, iter_timeout):
        kwargs = {"timeout_seconds": iter_timeout}
        if resource_version:
            kwargs["resource_version"] = resource_version
        if label_selector:
            kwargs["label_selector"] = label_selector
        return kwargs

    if namespace:
        list_fn = v1.list_namespaced_pod

        def list_kwargs_fn(resource_version, iter_timeout):
            kwargs = {
                "namespace": namespace,
                "timeout_seconds": iter_timeout,
            }
            if resource_version:
                kwargs["resource_version"] = resource_version
            if label_selector:
                kwargs["label_selector"] = label_selector
            return kwargs
    else:
        list_fn = v1.list_pod_for_all_namespaces

        def list_kwargs_fn(resource_version, iter_timeout):
            kwargs = {"timeout_seconds": iter_timeout}
            if resource_version:
                kwargs["resource_version"] = resource_version
            if label_selector:
                kwargs["label_selector"] = label_selector
            return kwargs

    collected, elapsed, error = await run_watch_loop(
        list_fn=list_fn,
        list_kwargs_fn=list_kwargs_fn,
        process_event_fn=_process_pod_event,
        ctx=ctx,
        timeout_seconds=timeout_seconds,
        max_events=max_events,
    )

    if error:
        return error

    if not collected:
        return (
            f"监听 {elapsed:.1f}s，未捕获到 Pod 状态变化\n"
            f"（namespace: {namespace or 'all'}，label_selector: {label_selector or 'all'}）"
        )

    added = sum(1 for e in collected if e and "🆕 Pod 新增" in e)
    modified = sum(1 for e in collected if e and "✏️ Pod 变更" in e)
    deleted = sum(1 for e in collected if e and "🗑️ Pod 删除" in e)

    lines = [
        f"Pod 监听结果（{elapsed:.1f}s，共 {len(collected)} 条变更）",
        f"  新增={added} | 变更={modified} | 删除={deleted}",
        "=" * 80,
    ]

    for item in collected:
        lines.append(item)
        lines.append("-" * 40)

    return "\n".join(lines)
