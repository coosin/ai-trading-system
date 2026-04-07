# OpenClaw Trading System - 生产环境Docker镜像

# ---- frontend build stage ----
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- backend runtime stage ----
FROM python:3.12-slim-bookworm

LABEL maintainer="OpenClaw Trading"
LABEL description="AI-Powered Cryptocurrency Trading System"
LABEL version="1.0.0"

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    netcat-openbsd \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 创建非root用户
RUN groupadd -r trader && useradd -r -g trader trader

# 创建工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY --chown=trader:trader src/ ./src/
COPY --chown=trader:trader config/ ./config/
COPY --chown=trader:trader frontend/ ./frontend/
COPY --from=frontend-build --chown=trader:trader /frontend/dist ./frontend/dist
COPY --chown=trader:trader workspace/ ./workspace/
COPY --chown=trader:trader .env.example ./.env.example
COPY --chown=trader:trader start_production.sh health_check.sh ./

# 创建必要目录并设置权限（包括记忆系统所需的所有子目录）
RUN mkdir -p logs \
    data/memory/daily \
    data/memory/long_term \
    data/memory/trade_records \
    data/memory/risk_events \
    data/models \
    data/historical \
    data/config \
    workspace/memory/daily \
    workspace/memory/long_term \
    workspace/memory/trade_records \
    backups/code \
    backups/config \
    backups/data && \
    chown -R trader:trader logs data workspace backups && \
    chmod -R 755 logs data workspace backups && \
    chmod +x start_production.sh health_check.sh

# 切换到非root用户
USER trader

# 健康检查
HEALTHCHECK --interval=60s --timeout=30s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令（模式由环境变量 MODE 决定，与 .env / compose 一致；勿在此硬编码）
CMD ["./start_production.sh"]
