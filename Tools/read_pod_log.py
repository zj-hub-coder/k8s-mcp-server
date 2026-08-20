from fastmcp import Context
from kubernetes.client.rest import ApiException

from app import mcp
from k8s_client import get_v1
from utils.pod_resolver import resolve_pods


def _pick_container(pod, container):
    """为 Pod 选择容器：指定则校验，单容器自动选，多容器报错。"""
    container_statuses = (pod.status.container_statuses or [])
    if not container_statuses:
        return None, "无可用容器状态（可能尚未调度）"

    if container:
        matched = [c for c in container_statuses if c.name == container]
        if matched:
            return container, None
        return None, (
            f"容器 '{container}' 不存在。"
            f"该 Pod 可用容器：{', '.join(c.name for c in container_statuses)}"
        )

    if len(container_statuses) == 1:
        return container_statuses[0].name, None

    return None, (
        f"该 Pod 包含 {len(container_statuses)} 个容器 "
        f"（{', '.join(c.name for c in container_statuses)}），请通过 container 参数指定。"
    )


def _read_single_pod_log(v1, namespace, pod_name, container, tail_lines, since_seconds, previous):
    """读取单个 Pod 的日志，返回文本。"""
    kwargs = {
        "name": pod_name,
        "namespace": namespace,
        "container": container,
        "previous": previous,
    }
    if tail_lines and tail_lines > 0:
        kwargs["tail_lines"] = tail_lines
    if since_seconds and since_seconds > 0:
        kwargs["since_seconds"] = since_seconds

    try:
        log = v1.read_namespaced_pod_log(**kwargs)
    except ApiException as e:
        return f"❌ 日志读取失败: {e.status} - {e.reason}"

    if not log or not log.strip():
        return (
            f"📭 {namespace}/{pod_name}/{container} 无日志输出"
            f"{'（前一个实例也无日志）' if previous else ''}"
        )
    return log


@mcp.tool(annotations={
    "title": "读取 Pod 日志",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def read_pod_log(
    pod_name: str = "",
    namespace: str = "",
    label_selector: str = "",
    workload: str = "",
    workload_type: str = "",
    container: str = "",
    tail_lines: int = 100,
    since_seconds: int = 0,
    previous: bool = False,
    ctx: Context = None,
) -> str:
    """读取 Pod 的容器日志（类似 kubectl logs）。

    支持三种定位 Pod 的方式（优先级从高到低）：
    1. label_selector：按标签筛选 Pod，如 "app=flannel"、"k8s-app=kube-dns"
    2. workload + workload_type：按工作负载名查找关联 Pod，如 "my-app" + "Deployment"
    3. pod_name：Pod 名称（支持前缀匹配，如 "flannel" 可匹配 "kube-flannel-ds-fz7pp"）

    匹配多个 Pod 时，自动拼接所有 Pod 的日志并加表头区分。

    Args:
        pod_name: Pod 名称（精确或前缀匹配）。与 label_selector/workload 二选一
        namespace: 命名空间。指定后缩小搜索范围；workload 模式必填
        label_selector: 标签选择器，如 "app=flannel"。最灵活的定位方式
        workload: 工作负载名称，如 "my-app"。与 workload_type 配合使用
        workload_type: 工作负载类型，支持 Deployment/DaemonSet/StatefulSet，默认 Deployment
        container: 容器名称。多容器 Pod 需指定；单容器自动选择
        tail_lines: 读取最近 N 行，默认 100。设 0 表示读取全部
        since_seconds: 仅读取最近 N 秒的日志，默认 0（不限）
        previous: 是否读取上一个容器实例的日志（排查 crash 重启），默认 False
    """
    if not (pod_name or label_selector or workload):
        return "❌ 请提供 pod_name、label_selector 或 workload 其中之一"

    if workload and not namespace:
        return "❌ workload 模式下 namespace 必填"

    v1 = get_v1()

    # ---- 解析 Pod 列表 ----
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

    # ---- 逐个读取日志 ----
    await ctx.info(
        f"共匹配 {len(pods)} 个 Pod，正在读取日志 "
        f"(tail={tail_lines}, previous={previous}, since={since_seconds}s)..."
    )

    parts = []
    for idx, (ns, name, pod) in enumerate(pods, 1):
        if pod.status is None:
            parts.append(
                f"===== Pod {idx}/{len(pods)}: {ns}/{name} =====\n"
                f"⚠️ Pod 尚未调度，无容器状态可读\n"
            )
            continue

        cname, err = _pick_container(pod, container)
        if err:
            parts.append(
                f"===== Pod {idx}/{len(pods)}: {ns}/{name} =====\n"
                f"⚠️ {err}\n"
            )
            continue

        log_text = _read_single_pod_log(
            v1, ns, name, cname, tail_lines, since_seconds, previous
        )
        header = f"===== Pod {idx}/{len(pods)}: {ns}/{name}/{cname} "
        if previous:
            header += "(previous instance) "
        header += "====="
        parts.append(f"{header}\n{log_text}")

    return "\n\n".join(parts)
