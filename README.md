# K8s 集群运维 MCP Server

基于 [FastMCP](https://github.com/jlowin/fastmcp) 的 Kubernetes 运维查询 MCP 服务。把 `kubectl get / describe / logs / events --watch` 等日常排查动作封装成 LLM 可调用的只读工具，让 Claude 等客户端直接读集群状态、快速定位故障。

> ⚠️ 本项目**只暴露只读工具**（无 create/update/delete）。但仍建议配合**只读 ServiceAccount** 的 RBAC 使用，见下文「安全建议」。

## 工具清单

| 工具 | 说明 | 对应 kubectl |
| --- | --- | --- |
| `list_nodes` | 节点列表概览 | `kubectl get nodes -o wide` |
| `get_node_detail` | 节点详情 | `kubectl describe node` |
| `get_node_resource_usage` | 节点资源请求/限制汇总与过载评估 | `describe node` 的 Allocated resources |
| `find_problem_nodes` | 扫描问题节点（NotReady / 各种 Pressure） | — |
| `list_pods` | Pod 列表（支持 namespace / label / field 过滤） | `kubectl get pods -o wide` |
| `get_pod_detail` | Pod 详情（支持 label / workload / 名称前缀定位） | `kubectl describe pod` |
| `read_pod_log` | 读取 Pod 容器日志 | `kubectl logs` |
| `query_events` | 查询集群事件（去重 + 排序） | `kubectl get events` |
| `watch_events` | 实时监听事件流 | `kubectl get events --watch` |
| `watch_nodes` | 实时监听节点状态变化 | `kubectl get nodes --watch` |
| `watch_pods` | 实时监听 Pod 状态变化 | `kubectl get pods --watch` |

另有 `@mcp.prompt`（节点排查 / 集群巡检引导）和 `@mcp.resource`（`k8s://cluster/summary` 集群摘要）两类附加能力。

## 目录结构

```
├── app.py              # FastMCP 实例（叶子模块，破循环导入）
├── k8s_server.py       # 入口：导入 Tools 即自动注册全部工具
├── k8s_client.py       # K8s 客户端懒加载 + 单一配置来源
├── config.py           # 12-Factor 环境变量配置
├── prompts.py          # @mcp.prompt 引导
├── resources.py        # @mcp.resource 资源
├── Tools/              # 每个工具一个文件，导入即注册
├── utils/              # 纯解析/辅助模块（无 K8s/MCP 依赖）
└── tests/              # 单元测试
```

## 安装与运行

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

# 2. 运行（HTTP transport，默认 127.0.0.1:8081）
python k8s_server.py
```

### 运行测试

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## 配置

全部通过环境变量配置，带默认值（见 `config.py`）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `KUBECONFIG_PATH` | `""` | 显式指定 kubeconfig 路径；留空走官方解析链（`$KUBECONFIG` → `~/.kube/config`） |
| `K8S_VERIFY_SSL` | `true` | 是否校验 TLS 证书；仅在调试自签且明确风险时置 `false` |
| `MCP_SERVER_NAME` | `k8s-node-server` | MCP 服务名 |
| `MCP_TRANSPORT` | `http` | 传输方式，`http` 或 `stdio` |
| `MCP_HOST` | `127.0.0.1` | 监听地址 |
| `MCP_PORT` | `8081` | 监听端口 |

K8s 连接配置加载优先级：**in-cluster（Pod 内 SA）→ 显式 `KUBECONFIG_PATH` → 官方 kubeconfig 解析链**，只取一份配置，不从多个文件拼装。

### 接入 MCP 客户端

以 Claude Code 为例（HTTP transport 已在 `127.0.0.1:8081` 运行时）：

```json
{
  "mcpServers": {
    "k8s-node-server": {
      "url": "http://127.0.0.1:8081/mcp"
    }
  }
}
```

## 安全建议

1. **使用只读 RBAC**：为运行本服务的 Pod / 用户配置只读 ClusterRole，避免借用高权限凭据。
2. **默认只绑定本机**：`MCP_HOST` 默认 `127.0.0.1`。如需对外暴露，务必在反代层加认证（TLS + Token / OIDC），因为 HTTP transport 本身**无认证与限流**。
3. **不要关闭证书校验**：`K8S_VERIFY_SSL=false` 仅用于临时调试自签证书，生产环境保持 `true`。
4. **凭据不入库**：kubeconfig 含密钥，`.gitignore` 已排除 `kubeconfig*`，切勿强制提交。

## 已知边界

- 所有工具为**只读**，不含变更操作（这是刻意设计）。
- `watch_*` 系列受全局并发锁限制：同一时刻只允许一个 watch 运行，避免给 API Server 加压。
- 事件/日志输出有长度上限，超大内容会被截断（见 `read_pod_log` 的截断逻辑与 `query_events` 的 `max_count`）。
