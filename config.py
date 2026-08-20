"""配置中心。

所有可变配置从环境变量读取并带默认值，遵循 12-Factor App 规范，
便于在本地 / 测试 / 生产环境间切换而无需改动代码。
"""

import os


# =============================================
# K8s 连接配置
# =============================================

# 本地开发使用的 kubeconfig 路径；集群内运行时走 inCluster，此项不生效
KUBECONFIG_PATH = os.getenv("KUBECONFIG_PATH", "")

# 是否校验 SSL 证书链路。
# 有真集群 + 私有/自签名 CA 通常需要设 true（且 kubeconfig 内嵌 CA 数据会自动参与校验）。
# 仅在调试自签证书未导入、且明确风险时，手动置 false。
VERIFY_SSL = os.getenv("K8S_VERIFY_SSL", "true").lower() == "true"


# =============================================
# MCP Server 配置
# =============================================

MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "k8s-node-server")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "http")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8081"))
