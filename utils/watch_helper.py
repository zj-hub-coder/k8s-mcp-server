"""通用 Watch 循环：timeout、410 Gone 处理、并发锁。

供 watch_events / watch_nodes / watch_pods 复用的底层循环，
上层只需提供「如何建立首次 watch」和「如何处理单条事件」两个钩子。
"""

import time

from kubernetes import watch as k8s_watch
from kubernetes.client.rest import ApiException

# 全局并发锁：整个项目同时只允许一个 watch 运行
_watch_active = False


async def run_watch_loop(
    list_fn,
    list_kwargs_fn,
    process_event_fn,
    ctx,
    timeout_seconds=30,
    max_events=100,
    min_timeout=5,
):
    """通用 Watch 循环。

    Args:
        list_fn:        K8s API 的 list_* 方法（如 v1.list_node）
        list_kwargs_fn: 函数(last_resource_version, iter_timeout) -> kwargs dict
                        根据是否有 resourceVersion 生成不同的调用参数
        process_event_fn: 函数(event_dict, state_dict) -> processed_item or None
                        处理单条 Watch 事件，返回 None 表示跳过（如无变化的 MODIFIED）
        ctx:            FastMCP Context（用于 ctx.info）
        timeout_seconds: 超时秒数
        max_events:     最多收集事件数
        min_timeout:    单次 watch 最小超时（避免 0 秒）

    Returns:
        (collected_events, elapsed_seconds, error_or_None)
    """
    global _watch_active
    if _watch_active:
        return [], 0, "⚠️ 当前已有 watch 正在运行，请稍后再试"

    _watch_active = True
    try:
        return await _do_run_watch_loop(
            list_fn, list_kwargs_fn, process_event_fn,
            ctx, timeout_seconds, max_events, min_timeout,
        )
    finally:
        _watch_active = False


async def _do_run_watch_loop(
    list_fn,
    list_kwargs_fn,
    process_event_fn,
    ctx,
    timeout_seconds,
    max_events,
    min_timeout,
):
    timeout_seconds = max(timeout_seconds, min_timeout)
    w = k8s_watch.Watch()
    collected = []
    start_time = time.monotonic()
    last_resource_version = None
    consecutive_410 = 0

    while time.monotonic() - start_time < timeout_seconds:
        remaining = timeout_seconds - (time.monotonic() - start_time)
        if remaining <= 0:
            break

        iter_timeout = int(max(min_timeout, remaining))

        try:
            kwargs = list_kwargs_fn(last_resource_version, iter_timeout)
            stream = w.stream(list_fn, **kwargs)

            for event in stream:
                if time.monotonic() - start_time >= timeout_seconds:
                    break
                if len(collected) >= max_events:
                    break

                # 410 Gone 处理
                if event.get("type") == "ERROR":
                    raw_obj = event.get("object", {})
                    code = getattr(raw_obj, "code", None)
                    if code == 410 or (isinstance(raw_obj, dict) and raw_obj.get("code") == 410):
                        await ctx.info("⚠️ 收到 410 Gone，重置 resourceVersion 重新连接...")
                        last_resource_version = None
                        consecutive_410 += 1
                        if consecutive_410 >= 5:
                            w.stop()
                            return collected, time.monotonic() - start_time, (
                                "⚠️ 连续收到 5 次 410 Gone，可能集群事件过多"
                            )
                        break
                    else:
                        collected.append(event)
                        continue

                # 更新 resourceVersion
                obj = event.get("object", {})
                rv = None
                if hasattr(obj, "metadata") and obj.metadata:
                    rv = obj.metadata.resource_version
                elif isinstance(obj, dict):
                    md = obj.get("metadata", {})
                    if md:
                        rv = md.get("resourceVersion")
                if rv:
                    last_resource_version = rv

                consecutive_410 = 0

                # 交给上层处理
                processed = process_event_fn(event, {})
                if processed is not None:
                    collected.append(processed)

        except ApiException as e:
            if e.status == 410:
                await ctx.info("⚠️ 收到 410 Gone（ApiException），重置 resourceVersion...")
                last_resource_version = None
                consecutive_410 += 1
                if consecutive_410 >= 5:
                    w.stop()
                    return collected, time.monotonic() - start_time, (
                        "⚠️ 连续收到 5 次 410 Gone，可能集群事件过多"
                    )
                continue
            elif e.status in (401, 403):
                w.stop()
                return collected, time.monotonic() - start_time, (
                    f"❌ 认证/授权失败: {e.status} - {e.reason}"
                )
            else:
                await ctx.info(f"⚠️ 监听异常({e.status})，跳过本轮: {e.reason}")
                time.sleep(2)
                continue
        except Exception as e:
            await ctx.info(f"⚠️ 监听异常，跳过本轮: {str(e)[:100]}")
            time.sleep(2)
            continue

    w.stop()
    return collected, time.monotonic() - start_time, None
