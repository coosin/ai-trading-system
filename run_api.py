#!/usr/bin/env python3
"""启动API服务器"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.modules.api.server import APIServer

async def main():
    """主函数"""
    # 创建API服务器
    api_server = APIServer(host="0.0.0.0", port=8000)
    await api_server.initialize()
    
    # 获取FastAPI app
    app = api_server.app
    
    if app is None:
        print("错误: FastAPI应用初始化失败")
        return
    
    # 使用uvicorn运行
    import uvicorn
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
