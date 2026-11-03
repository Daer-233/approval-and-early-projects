"""
一键启动 MCP 服务 (streamable-http)
等价于原来的 start_mcp_conda.ps1

用法:
    python run_mcp.py
"""

import sys
import os

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

if __name__ == "__main__":
    # 设置环境变量（等价于原来 PS 脚本中的 $env:xxx）
    os.environ["LOL_INTENT_MODEL_DIR"] = "models/lol-bert-binary-intent"
    os.environ["MCP_HOST"] = "0.0.0.0"
    os.environ["MCP_PORT"] = "8008"

    from lol_intent.mcp_server import parse_args, mcp

    args = parse_args(["--transport", "streamable-http"])
    mcp.run(transport=args.transport)
