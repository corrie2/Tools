#!/usr/bin/env python3
"""记忆库监控面板启动脚本"""

import argparse
import os
import sys
from pathlib import Path

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

# 加载 .env 文件
def load_dotenv(env_path: Path):
    """简单加载 .env 文件"""
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

load_dotenv(Path(__file__).parent / ".env")


def main():
    parser = argparse.ArgumentParser(description="Agent Long Memory 监控面板")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8081, help="监听端口 (默认: 8081)")
    parser.add_argument("--reload", action="store_true", help="自动重载")
    
    args = parser.parse_args()
    
    try:
        import uvicorn
        from agent_long_memory.monitor_api import app
        
        print(f"启动记忆库监控面板...")
        print(f"访问地址: http://{args.host}:{args.port}")
        print(f"按 Ctrl+C 停止")
        
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError as e:
        print(f"错误: 缺少依赖 - {e}")
        print("请安装: pip install uvicorn fastapi")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
