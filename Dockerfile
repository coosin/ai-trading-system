# OpenClaw Trading System - Docker生产部署配置
FROM python:3.12-slim

LABEL maintainer="OpenClaw Trading"
LABEL description="AI-Powered Cryptocurrency Trading System"

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY src/ ./src/
COPY config/ ./config/
COPY workspace/ ./workspace/
COPY data/ ./data/
COPY .env.example ./.env.example
COPY start_production.sh health_check.sh ./

# 创建必要目录
RUN mkdir -p logs data/memory data/models data/historical

# 设置权限
RUN chmod +x start_production.sh health_check.sh

# 健康检查
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["./start_production.sh", "simulation"]
