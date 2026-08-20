"""K8s 集群节点运维 MCP Server 入口。

提供节点维度的运维查询能力：
  - list_nodes:              节点列表概览（kubectl get nodes -o wide）
  - get_node_detail:         节点详情（kubectl describe node）
  - get_node_resource_usage: 节点资源使用评估
  - find_problem_nodes:      问题节点扫描

导入 Tools 包即自动注册全部 @mcp.tool() 工具。
"""

import Tools  # noqa: F401    导入即注册全部 @mcp.tool() 工具
import prompts  # noqa: F401  导入即注册全部 @mcp.prompt() 引导
import resources  # noqa: F401  导入即注册全部 @mcp.resource() 资源
import config
from app import mcp

# =============================================
# 入口
# =============================================

if __name__ == "__main__":
    mcp.run(transport=config.MCP_TRANSPORT, host=config.MCP_HOST, port=config.MCP_PORT)
    #mcp.run(transport="stdio")