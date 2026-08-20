"""Pod 定位解析：按 label_selector / workload / pod_name 多入口查找 Pod。"""

from kubernetes.client import AppsV1Api
from kubernetes.client.rest import ApiException


def resolve_pods(v1, pod_name, namespace, label_selector, workload, workload_type):
    """多入口解析 Pod 列表，返回 [(namespace, pod_name, pod_obj), ...]。

    优先级: label_selector > workload > pod_name。
    """
    if label_selector:
        kwargs = {"label_selector": label_selector}
        if namespace:
            pods = v1.list_namespaced_pod(namespace=namespace, **kwargs)
        else:
            pods = v1.list_pod_for_all_namespaces(**kwargs)
        return [(p.metadata.namespace, p.metadata.name, p) for p in pods.items]

    if workload:
        apps_v1 = AppsV1Api()
        wt = (workload_type or "Deployment").capitalize()
        if wt == "Deployment":
            obj = apps_v1.read_namespaced_deployment(workload, namespace)
            selector = obj.spec.selector.match_labels or {}
        elif wt == "Daemonset":
            obj = apps_v1.read_namespaced_daemon_set(workload, namespace)
            selector = obj.spec.selector.match_labels or {}
        elif wt == "Statefulset":
            obj = apps_v1.read_namespaced_stateful_set(workload, namespace)
            selector = obj.spec.selector.match_labels or {}
        else:
            raise ValueError(f"不支持的 workload_type: {wt}")

        if not selector:
            raise ValueError(f"{wt} '{namespace}/{workload}' 无 selector")
        label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
        pods = v1.list_pod_for_all_namespaces(label_selector=label_selector)
        return [(p.metadata.namespace, p.metadata.name, p) for p in pods.items]

    if pod_name:
        if namespace:
            try:
                pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
                return [(namespace, pod_name, pod)]
            except ApiException as e:
                if e.status != 404:
                    raise
                return []
        pods = v1.list_pod_for_all_namespaces()
        # Deployment 等生成的 Pod 名带 "-<hash>" 后缀，前缀匹配才能按工作负载名找到它们
        matched = [
            (p.metadata.namespace, p.metadata.name, p)
            for p in pods.items
            if p.metadata.name == pod_name or p.metadata.name.startswith(pod_name + "-")
        ]
        return matched

    return []
