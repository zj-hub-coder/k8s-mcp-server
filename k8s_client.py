"""Kubernetes 客户端管理：初始化与懒加载获取。

加载优先级：
1) in-cluster (Pod 内部 SA + CA)
2) 显式配置：若环境变量 KUBECONFIG_PATH 指向存在的文件 → 使用该路径
3) kubernetes 官方 kubeconfig 解析链（$KUBECONFIG 环境变量 → ~/.kube/config）
"""

import os

from kubernetes import client
from kubernetes import config as k8s_config

import config

_k8s_v1 = None
_k8s_apps_v1 = None


def _resolve_kubeconfig_path() -> str | None:
    """判断是否有用户显式指定的 kubeconfig 文件路径存在。

    没有显式路径或文件不存在时返回 None，表示走 kubernetes 客户端标准解析链。
    """
    env_path = os.getenv("KUBECONFIG_PATH")
    # 仅在显式设置过环境变量时才用它；否则交给官方 kubeconfig 解析链
    if env_path and os.path.isfile(env_path):
        return env_path
    default_path = os.path.expandvars(os.path.expanduser(config.KUBECONFIG_PATH))
    if os.path.isfile(default_path):
        return default_path
    return None


def init_k8s_client():
    """初始化 Kubernetes API 客户端。

    只取一份配置：in-cluster / 显式文件 / 官方解析链三选一，不从多个文件拼装。
    """
    global _k8s_v1
    try:
        k8s_config.load_incluster_config()  # 集群内 Pod 运行时使用
    except Exception:
        explicit = _resolve_kubeconfig_path()
        if explicit is not None:
            k8s_config.load_kube_config(config_file=explicit)
        else:
            # 官方标准解析链：$KUBECONFIG env → ~/.kube/config
            k8s_config.load_kube_config()

    # TLS 策略：默认严格校验；仅显式开关 + 已知自签场景才关闭
    configuration = client.Configuration.get_default_copy()
    configuration.verify_ssl = config.VERIFY_SSL
    client.Configuration.set_default(configuration)

    # 创建 API 客户端实例
    _k8s_v1 = client.CoreV1Api()


def get_v1() -> client.CoreV1Api:
    """获取 K8s CoreV1Api 客户端（懒加载）。"""
    global _k8s_v1
    if _k8s_v1 is None:
        init_k8s_client()
    return _k8s_v1


def get_apps_v1() -> client.AppsV1Api:
    """获取 K8s AppsV1Api 客户端（懒加载），与 CoreV1Api 共享同一套连接配置。

    Deployment/DaemonSet/StatefulSet 等 Workload 查询走这里，
    避免在工具里直接 new AppsV1Api() 而绕过统一配置路径。
    """
    global _k8s_apps_v1
    if _k8s_apps_v1 is None:
        get_v1()  # 复用懒加载，确保连接配置已初始化
        _k8s_apps_v1 = client.AppsV1Api()
    return _k8s_apps_v1

