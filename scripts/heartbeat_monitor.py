#!/usr/bin/env python3
"""
交易系统心跳监控脚本
用于定期检查系统状态
"""

import os
import sys
import logging
from datetime import datetime

# 添加系统路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_system_status():
    """检查交易系统状态"""
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "system": "ai-trading-system",
        "status": "unknown",
        "components": {},
        "alerts": []
    }
    
    try:
        # 1. 检查主进程
        import psutil
        
        trading_process = None
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if 'trading' in cmdline.lower() or 'start.py' in cmdline or 'trading_system' in cmdline:
                    trading_process = proc
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if trading_process:
            status["components"]["main_process"] = {
                "pid": trading_process.info['pid'],
                "status": "running",
                "cpu_percent": trading_process.cpu_percent(interval=0.1),
                "memory_mb": trading_process.memory_info().rss / 1024 / 1024
            }
            status["status"] = "running"
        else:
            status["components"]["main_process"] = {"status": "stopped"}
            status["status"] = "stopped"
            status["alerts"].append("主交易进程未运行")
        
        # 2. 检查数据目录
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        if os.path.exists(data_dir):
            status["components"]["data_directory"] = {
                "status": "exists",
                "size_mb": sum(os.path.getsize(os.path.join(dirpath, filename)) 
                              for dirpath, dirnames, filenames in os.walk(data_dir) 
                              for filename in filenames) / 1024 / 1024
            }
        else:
            status["components"]["data_directory"] = {"status": "missing"}
            status["alerts"].append("数据目录不存在")
        
        # 3. 检查日志目录
        logs_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
        if os.path.exists(logs_dir):
            log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
            status["components"]["logs_directory"] = {
                "status": "exists",
                "log_count": len(log_files),
                "latest_log": max([os.path.join(logs_dir, f) for f in log_files], 
                                 key=os.path.getmtime) if log_files else None
            }
        else:
            status["components"]["logs_directory"] = {"status": "missing"}
        
        # 4. 检查配置文件
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        if os.path.exists(config_dir):
            config_files = [f for f in os.listdir(config_dir) if f.endswith(('.yaml', '.yml', '.json', '.ini'))]
            status["components"]["config_directory"] = {
                "status": "exists",
                "config_count": len(config_files)
            }
        else:
            status["components"]["config_directory"] = {"status": "missing"}
            status["alerts"].append("配置目录不存在")
        
        # 5. 检查API端口（如果有的话）
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 8000))
            sock.close()
            status["components"]["api_port"] = {
                "port": 8000,
                "status": "open" if result == 0 else "closed"
            }
            if result != 0:
                status["alerts"].append("API端口8000未监听")
        except Exception as e:
            status["components"]["api_port"] = {"status": "error", "error": str(e)}
        
    except ImportError as e:
        status["status"] = "error"
        status["components"]["dependencies"] = {"status": "missing", "missing": str(e)}
        status["alerts"].append(f"缺少依赖: {e}")
    except Exception as e:
        status["status"] = "error"
        status["components"]["monitoring_error"] = {"error": str(e)}
        status["alerts"].append(f"监控错误: {e}")
    
    return status

def main():
    """主函数"""
    print("🔍 交易系统心跳检查")
    print("=" * 50)
    
    status = check_system_status()
    
    print(f"⏰ 检查时间: {status['timestamp']}")
    print(f"📊 系统状态: {status['status'].upper()}")
    
    # 显示组件状态
    print("\n📦 组件状态:")
    for component, info in status["components"].items():
        if isinstance(info, dict):
            comp_status = info.get("status", "unknown")
            print(f"  • {component}: {comp_status}")
            if comp_status in ["running", "exists"]:
                for key, value in info.items():
                    if key != "status" and value is not None:
                        print(f"    - {key}: {value}")
    
    # 显示警报
    if status["alerts"]:
        print(f"\n🚨 警报 ({len(status['alerts'])}个):")
        for alert in status["alerts"]:
            print(f"  ⚠️  {alert}")
    else:
        print("\n✅ 无警报")
    
    print("=" * 50)
    
    # 返回退出码
    if status["status"] == "error" or status["alerts"]:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())