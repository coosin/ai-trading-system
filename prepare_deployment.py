#!/usr/bin/env python3
"""
部署准备脚本
检查系统依赖、配置文件和环境变量，确保系统可以正常部署
"""

import os
import sys
import logging
import subprocess
import json
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_dependencies():
    """检查系统依赖"""
    logger.info("🔍 检查系统依赖...")
    
    # 检查Python版本
    python_version = sys.version_info
    if python_version < (3, 9):
        logger.error(f"Python版本过低: {python_version.major}.{python_version.minor}.{python_version.micro}")
        logger.error("需要Python 3.9或更高版本")
        return False
    logger.info(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # 检查Docker和Docker Compose
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Docker未安装")
            return False
        logger.info(f"✅ Docker: {result.stdout.strip()}")
    except Exception as e:
        logger.error(f"检查Docker失败: {e}")
        return False
    
    try:
        result = subprocess.run(["docker-compose", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Docker Compose未安装")
            return False
        logger.info(f"✅ Docker Compose: {result.stdout.strip()}")
    except Exception as e:
        logger.error(f"检查Docker Compose失败: {e}")
        return False
    
    # 检查必要的目录
    required_dirs = ["config", "data", "logs"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            dir_path.mkdir(exist_ok=True)
            logger.info(f"✅ 创建目录: {dir_name}")
        else:
            logger.info(f"✅ 目录已存在: {dir_name}")
    
    return True

def check_config_files():
    """检查配置文件"""
    logger.info("🔍 检查配置文件...")
    
    # 主可调配置：config/openclaw.yml（default.yml 仅为兼容占位）
    primary_config = Path("config/openclaw.yml")
    if not primary_config.exists():
        logger.warning("主配置文件 config/openclaw.yml 不存在，将创建默认配置")
        # 创建默认配置
        default_config_content = {
            "system": {
                "name": "AI Trading System",
                "version": "1.0.0",
                "debug": False,
                "log_level": "INFO"
            },
            "trading": {
                "enabled": True,
                "paper_trading": True,
                "max_position_size": 0.1,
                "max_daily_loss": 0.02,
                "max_position_count": 10,
                "commission_rate": 0.001,
                "slippage_rate": 0.0005
            },
            "risk": {
                "enabled": True,
                "max_drawdown": 0.1,
                "var_limit": 0.05,
                "position_limit": 0.2
            },
            "data": {
                "update_interval": 60,
                "history_days": 365,
                "symbols": ["BTC/USDT", "ETH/USDT"]
            },
            "monitoring": {
                "enabled": True,
                "health_check_interval": 30,
                "metrics_interval": 60
            },
            "notification": {
                "telegram": {
                    "enabled": False,
                    "token": "",
                    "chat_id": ""
                },
                "email": {
                    "enabled": False,
                    "smtp_server": "",
                    "smtp_port": 587,
                    "username": "",
                    "password": "",
                    "from_email": "",
                    "to_email": ""
                }
            }
        }
        
        import yaml
        primary_config.parent.mkdir(parents=True, exist_ok=True)
        with open(primary_config, 'w', encoding='utf-8') as f:
            yaml.dump(default_config_content, f, default_flow_style=False, allow_unicode=True)
        logger.info("✅ 创建主配置文件 config/openclaw.yml")
    else:
        logger.info("✅ 主配置文件存在: config/openclaw.yml")
    
    # 检查生产环境配置文件
    production_config = Path("config/production.yml")
    if not production_config.exists():
        logger.warning("生产环境配置文件不存在，将创建生产环境配置")
        # 创建生产环境配置
        production_config_content = {
            "system": {
                "debug": False,
                "log_level": "INFO"
            },
            "trading": {
                "paper_trading": False
            }
        }
        
        import yaml
        with open(production_config, 'w', encoding='utf-8') as f:
            yaml.dump(production_config_content, f, default_flow_style=False, allow_unicode=True)
        logger.info("✅ 创建生产环境配置文件")
    else:
        logger.info("✅ 生产环境配置文件存在")
    
    return True

def check_environment_variables():
    """检查环境变量"""
    logger.info("🔍 检查环境变量...")
    
    # 检查必要的环境变量
    required_env_vars = [
        "TRADING_ENV",
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY"
    ]
    
    for env_var in required_env_vars:
        if env_var not in os.environ:
            logger.warning(f"环境变量 {env_var} 未设置")
            # 对于开发环境，设置默认值
            if env_var == "TRADING_ENV" and "TRADING_ENV" not in os.environ:
                os.environ["TRADING_ENV"] = "development"
                logger.info("✅ 设置默认环境变量: TRADING_ENV=development")
            elif env_var == "DATABASE_URL" and "DATABASE_URL" not in os.environ:
                os.environ["DATABASE_URL"] = "postgresql://admin:password@localhost:5432/trading"
                logger.info("✅ 设置默认环境变量: DATABASE_URL=postgresql://admin:password@localhost:5432/trading")
            elif env_var == "REDIS_URL" and "REDIS_URL" not in os.environ:
                os.environ["REDIS_URL"] = "redis://localhost:6379/0"
                logger.info("✅ 设置默认环境变量: REDIS_URL=redis://localhost:6379/0")
            elif env_var == "SECRET_KEY" and "SECRET_KEY" not in os.environ:
                import secrets
                os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)
                logger.info("✅ 设置默认环境变量: SECRET_KEY=随机生成")
        else:
            logger.info(f"✅ 环境变量 {env_var} 已设置")
    
    return True

def check_docker_compose():
    """检查Docker Compose配置"""
    logger.info("🔍 检查Docker Compose配置...")
    
    # 检查docker-compose.yml文件
    docker_compose_file = Path("docker-compose.yml")
    if not docker_compose_file.exists():
        logger.error("docker-compose.yml文件不存在")
        return False
    logger.info("✅ docker-compose.yml文件存在")
    
    # 检查prometheus.yml文件
    prometheus_config = Path("prometheus.yml")
    if not prometheus_config.exists():
        logger.warning("prometheus.yml文件不存在，将创建默认配置")
        # 创建默认prometheus配置
        prometheus_config_content = {
            "global": {
                "scrape_interval": "15s",
                "evaluation_interval": "15s"
            },
            "scrape_configs": [
                {
                    "job_name": "trading-app",
                    "scrape_interval": "5s",
                    "static_configs": [
                        {
                            "targets": ["trading-app:8000"]
                        }
                    ]
                }
            ]
        }
        
        import yaml
        with open(prometheus_config, 'w', encoding='utf-8') as f:
            yaml.dump(prometheus_config_content, f, default_flow_style=False, allow_unicode=True)
        logger.info("✅ 创建默认prometheus.yml配置文件")
    else:
        logger.info("✅ prometheus.yml文件存在")
    
    return True

def check_frontend():
    """检查前端配置"""
    logger.info("🔍 检查前端配置...")
    
    # 检查前端目录
    frontend_dir = Path("frontend")
    if not frontend_dir.exists():
        logger.warning("前端目录不存在")
        return False
    logger.info("✅ 前端目录存在")
    
    # 检查前端依赖
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        logger.warning("前端package.json文件不存在")
        return False
    logger.info("✅ 前端package.json文件存在")
    
    return True

def main():
    """主函数"""
    logger.info("🚀 开始部署准备...")
    
    # 检查所有依赖和配置
    checks = [
        check_dependencies,
        check_config_files,
        check_environment_variables,
        check_docker_compose,
        check_frontend
    ]
    
    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
    
    if all_passed:
        logger.info("🎉 部署准备完成！所有检查都通过了")
        logger.info("\n📋 部署步骤:")
        logger.info("1. 构建Docker镜像: docker-compose build")
        logger.info("2. 启动服务: docker-compose up -d")
        logger.info("3. 检查服务状态: docker-compose ps")
        logger.info("4. 访问应用: http://localhost:8000")
        logger.info("5. 访问监控面板: http://localhost:3000 (用户名: admin, 密码: admin)")
    else:
        logger.error("❌ 部署准备失败，存在一些问题需要解决")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
