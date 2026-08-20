from fastmcp import Context

from app import mcp
from k8s_client import get_v1
from utils.watch_helper import run_watch_loop
from utils.parse_watch import (
    _node_snapshot,
    format_node_watch,
)

# 记录节点上一次的状态快照，用于变更对比
_node_snapshots = {}


def _process_node_event(event, _state):
    """处理单条 Node Watch 事件。"""
    event_type = event.get("type", "???")
    obj = event.get("object", {})

    # 兼容字典（已解析的 object）和对象（kubernetes 客户端返回的对象）
    if isinstance(obj, dict):
        return None  # Event 流是字典，但 Node/Pod 流是对象，跳过错误格式

    node = obj
    node_name = node.metadata.name

    old_snap = _node_snapshots.get(node_name)
    formatted = format_node_watch(event_type, node, old_snap)

    # 更新快照
    if event_type in ("ADDED", "MODIFIED"):
        _node_snapshots[node_name] = _node_snapshot(node)
    elif event_type == "DELETED" and node_name in _node_snapshots:
        del _node_snapshots[node_name]

    return formatted


@mcp.tool(annotations={
    "title": "实时监听节点变化",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def watch_nodes(
    label_selector: str = "",
    timeout_seconds: int = 30,
    max_events: int = 100,
    ctx: Context = None,
) -> str:
    """实时监听 K8s 节点状态变化（类似 kubectl get nodes --watch）。

    捕捉节点 Ready/NotReady、MemoryPressure、DiskPressure、PIDPressure、
    SchedulingDisabled 等状态变化，只在有实质变更时输出。

    Args:
        label_selector: 标签选择器，过滤节点
        timeout_seconds: 监听超时秒数，默认 30，最小 5
        max_events: 最多收集的事件数，达到后提前退出
    """
    v1 = get_v1()

    # 预热：先拉一次当前节点状态作为变更对比基线
    try:
        if label_selector:
            nodes = v1.list_node(label_selector=label_selector)
        else:
            nodes = v1.list_node()
        for node in nodes.items:
            _node_snapshots[node.metadata.name] = _node_snapshot(node)
        await ctx.info(f"基线加载完成：{len(_node_snapshots)} 个节点")
    except Exception as e:
        await ctx.info(f"⚠️ 基线加载失败（非致命）：{str(e)[:100]}")

    await ctx.info(
        f"开始监听节点 | label_selector: {label_selector or 'all'} | "
        f"超时: {timeout_seconds}s"
    )

    def list_kwargs_fn(resource_version, iter_timeout):
        kwargs = {"timeout_seconds": iter_timeout}
        if resource_version:
            kwargs["resource_version"] = resource_version
        if label_selector:
            kwargs["label_selector"] = label_selector
        return kwargs

    collected, elapsed, error = await run_watch_loop(
        list_fn=v1.list_node,
        list_kwargs_fn=list_kwargs_fn,
        process_event_fn=_process_node_event,
        ctx=ctx,
        timeout_seconds=timeout_seconds,
        max_events=max_events,
    )

    if error:
        return error

    if not collected:
        return (
            f"监听 {elapsed:.1f}s，未捕获到节点状态变化\n"
            f"（label_selector: {label_selector or 'all'}）"
        )

    added = sum(1 for e in collected if e and e.startswith("🆕"))
    modified = sum(1 for e in collected if e and e.startswith("✏️"))
    deleted = sum(1 for e in collected if e and e.startswith("🗑️"))

    lines = [
        f"节点监听结果（{elapsed:.1f}s，共 {len(collected)} 条变更）",
        f"  新增={added} | 变更={modified} | 删除={deleted}",
        "=" * 80,
    ]

    for item in collected:
        lines.append(item)
        lines.append("-" * 40)

    return "\n".join(lines)
