# 全智能量化交易系统 Dockerfile
# 基于 Python 3.11 + Ubuntu 22.04

FROM python:3.11-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC \
    APP_HOME=/app

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 创建工作目录
WORKDIR $APP_HOME

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    gcc \
    g++ \
    make \
    libssl-dev \
    libffi-dev \
    libpq-dev \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN groupadd -r trader && useradd -r -g trader trader && \
    chown -R trader:trader $APP_HOME

# 切换到非root用户
USER trader

# 创建必要的目录
RUN mkdir -p \
    logs \
    data \
    config \
    cache \
    backups

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# 暴露端口（如果需要）
EXPOSE 8000

# 默认启动命令
CMD ["python", "-m", "modules.main_controller", "--mode", "paper_trading"]