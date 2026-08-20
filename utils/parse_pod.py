"""Pod 对象解析：从 V1Pod 提取结构化概要信息。"""


def _parse_pod(pod) -> dict:
    """从 V1Pod 对象中提取关键信息，返回结构化字典。

    包含：基本信息、容器状态（Ready/Restarts/Waiting/Terminated）、
          资源请求与限制、标签、注解、Conditions。
    """
    metadata = pod.metadata
    spec = pod.spec
    status = pod.status

    # Pod 可能尚未调度，status 为 None
    if status is None:
        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "uid": metadata.uid,
            "phase": "Pending",
            "node": spec.node_name if spec else "",
            "pod_ip": "N/A",
            "host_ip": "N/A",
            "restart_policy": spec.restart_policy if spec else "",
            "labels": dict(metadata.labels or {}),
            "annotations": dict(metadata.annotations or {}),
            "containers_statuses": [],
            "containers_resources": [
                {
                    "name": c.name,
                    "image": c.image,
                    "requests": dict(c.resources.requests) if c.resources and c.resources.requests else {},
                    "limits": dict(c.resources.limits) if c.resources and c.resources.limits else {},
                }
                for c in (spec.containers or [])
            ],
            "conditions": {"PodScheduled": {"status": "False", "reason": "NotScheduled", "message": "Pod 尚未调度"}},
            "qos_class": "",
            "start_time": "",
            "_warning": "Pod status 为 None（可能尚未被调度器处理）",
        }

    # ---- 容器状态（核心） ----
    containers_info = []
    for cs in (status.container_statuses or []):
        state_detail = {}
        if cs.state.waiting:
            state_detail["waiting"] = {
                "reason": cs.state.waiting.reason or "",
                "message": cs.state.waiting.message or "",
            }
        if cs.state.terminated:
            state_detail["terminated"] = {
                "reason": cs.state.terminated.reason or "",
                "exit_code": cs.state.terminated.exit_code or 0,
                "started_at": str(cs.state.terminated.started_at or ""),
                "finished_at": str(cs.state.terminated.finished_at or ""),
                "container_id": cs.state.terminated.container_id or "",
            }
        if cs.state.running:
            state_detail["running"] = {
                "started_at": str(cs.state.running.started_at or ""),
            }
        if not state_detail:
            state_detail = {"status": "unknown"}

        # 上一次终止状态（区分 previous 日志场景）
        last_state = {}
        if cs.last_state and cs.last_state.terminated:
            last_state["terminated"] = {
                "reason": cs.last_state.terminated.reason or "",
                "exit_code": cs.last_state.terminated.exit_code or 0,
            }

        containers_info.append({
            "name": cs.name,
            "ready": cs.ready,
            "restart_count": cs.restart_count,
            "image": cs.image,
            "state": state_detail,
            "last_state": last_state,
            "container_id": cs.container_id or "",
        })

    # ---- 资源请求/限制（从 spec 取期望，更贴近调度视角） ----
    container_resources = []
    for c in (spec.containers or []):
        requests = {}
        limits = {}
        if c.resources and c.resources.requests:
            requests = dict(c.resources.requests)
        if c.resources and c.resources.limits:
            limits = dict(c.resources.limits)
        container_resources.append({
            "name": c.name,
            "image": c.image,
            "requests": requests,
            "limits": limits,
        })

    # ---- Conditions ----
    conditions = {}
    for cond in (status.conditions or []):
        conditions[cond.type] = {
            "status": cond.status,
            "reason": cond.reason or "",
            "message": cond.message or "",
        }

    # ---- Phase 可读状态 ----
    phase = status.phase or "Unknown"
    if status.phase == "Pending":
        reason = conditions.get("PodScheduled", {}).get("reason", "")
        if reason:
            phase = f"Pending({reason})"

    return {
        "name": metadata.name,
        "namespace": metadata.namespace,
        "uid": metadata.uid,
        "phase": phase,
        "node": spec.node_name or "",
        "pod_ip": status.pod_ip or "N/A",
        "host_ip": status.host_ip or "N/A",
        "restart_policy": spec.restart_policy,
        "labels": dict(metadata.labels or {}),
        "annotations": dict(metadata.annotations or {}),
        "containers_statuses": containers_info,
        "containers_resources": container_resources,
        "conditions": conditions,
        "qos_class": status.qos_class or "",
        "start_time": str(status.start_time or ""),
    }
