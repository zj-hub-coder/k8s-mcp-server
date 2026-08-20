"""Tools 包：导入即注册全部 MCP 工具。

只需 `import Tools` 即可触发所有工具的 @mcp.tool() 装饰器注册。
"""

from . import list_nodes  # noqa: F401
from . import get_node_detail  # noqa: F401
from . import get_node_resource_usage  # noqa: F401
from . import find_problem_nodes  # noqa: F401
from . import get_pod_detail  # noqa: F401
from . import read_pod_log  # noqa: F401
from . import list_pods  # noqa: F401
from . import query_events  # noqa: F401
from . import watch_events  # noqa: F401
from . import watch_nodes  # noqa: F401
from . import watch_pods  # noqa: F401
