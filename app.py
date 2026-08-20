"""MCP Server 实例。

单独成模块是为了打破「入口(k8s_server) ↔ 工具(Tools)」的循环导入：
工具文件需要 mcp 来注册，入口又需要导入工具触发注册，
把 mcp 放在无下游依赖的叶子模块里即可让依赖单向流动。
"""

from fastmcp import FastMCP

from config import MCP_SERVER_NAME

mcp = FastMCP(MCP_SERVER_NAME)
