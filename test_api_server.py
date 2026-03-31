#!/usr/bin/env python3
"""
API服务器测试脚本
"""

import subprocess
import time

def test_api_server():
    """测试API服务器"""
    print("🔍 测试API服务器...")
    
    # 启动API服务器（使用后台进程）
    server_script = '''
from src.modules.api.server import APIServer
import asyncio
import json
from datetime import datetime

async def run():
    api = APIServer(host="127.0.0.1", port=8000)
    await api.initialize()
    success = await api.start()
    print(f"API服务器启动: {'成功' if success else '失败'}")
    
    if success:
        # 注册自定义路由
        @api.app.get("/api/v1/market/{symbol}", tags=["market"])
        async def get_market_data(symbol: str):
            """获取市场数据"""
            return {
                "symbol": symbol,
                "price": 50000.0,
                "volume": 1000.0,
                "timestamp": datetime.now().isoformat(),
            }
        
        # 运行一段时间
        print("API服务器运行中...")
        await asyncio.sleep(30)
        
    await api.stop()
    await api.cleanup()
    print("API服务器已停止")

asyncio.run(run())
'''
    
    server_process = subprocess.Popen(
        ["python3", "-c", server_script],
        cwd=".",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    time.sleep(10)  # 给服务器更多启动时间
    
    # 测试健康检查接口
    print("🧪 测试健康检查接口...")
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8000/health"],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"健康检查响应: {result.stdout}")
        print(f"状态码: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ 健康检查接口正常")
        else:
            print("❌ 健康检查接口失败")
    except Exception as e:
        print(f"❌ 健康检查接口测试失败: {e}")
    
    # 测试API文档接口
    print("🧪 测试API文档接口...")
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8000/docs"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ API文档接口正常")
        else:
            print("❌ API文档接口失败")
    except Exception as e:
        print(f"❌ API文档接口测试失败: {e}")
    
    # 测试API状态接口
    print("🧪 测试API状态接口...")
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8000/api/v1/status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"状态接口响应: {result.stdout}")
        print(f"状态码: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ API状态接口正常")
        else:
            print("❌ API状态接口失败")
    except Exception as e:
        print(f"❌ API状态接口测试失败: {e}")
    
    # 测试登录接口
    print("🧪 测试登录接口...")
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", "http://localhost:8000/auth/login", 
             "-H", "Content-Type: application/json",
             "-d", '{"username":"admin","password":"admin123"}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"登录接口响应: {result.stdout}")
        print(f"状态码: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ 登录接口正常")
        else:
            print("❌ 登录接口失败")
    except Exception as e:
        print(f"❌ 登录接口测试失败: {e}")
    
    # 等待服务器运行完成
    print("⏳ 等待服务器运行完成...")
    try:
        stdout, stderr = server_process.communicate(timeout=20)
        print(f"服务器输出: {stdout}")
        if stderr:
            print(f"服务器错误: {stderr}")
        print("✅ API服务器测试完成")
    except subprocess.TimeoutExpired:
        server_process.kill()
        print("⚠️  API服务器被强制终止")

if __name__ == "__main__":
    test_api_server()
