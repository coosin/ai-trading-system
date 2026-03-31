FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 18789
EXPOSE 18790

# 设置环境变量
ENV OPENCLAW_STATE_DIR=/app/data
ENV OPENCLAW_CONFIG_PATH=/app/openclaw-trading.json
ENV OPENCLAW_GATEWAY_PORT=18790

# 创建数据目录
RUN mkdir -p /app/data

# 启动命令
CMD ["python", "-m", "src.main"]
