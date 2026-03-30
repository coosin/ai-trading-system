# 第一阶段：构建环境
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt requirements-dev.txt* ./

# 创建虚拟环境并安装依赖
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

# 第二阶段：运行环境
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制虚拟环境
COPY --from=builder /venv /venv

# 复制项目文件（只复制必要的文件）
COPY src/ src/
COPY requirements.txt .

# 创建数据目录
RUN mkdir -p data/config data/logs data/models \
    && chmod -R 755 data/

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV TRADING_ENV=production
ENV PYTHONPATH=/app
ENV PATH="/venv/bin:$PATH"

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 启动命令（使用gunicorn提高性能）
CMD ["gunicorn", "src.web.app:app", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "300"]
