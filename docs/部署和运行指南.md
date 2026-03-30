# 全智能量化交易系统 - 部署和运行指南

## 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [手动部署](#手动部署)
- [Docker部署](#docker部署)
- [配置说明](#配置说明)
- [常见问题](#常见问题)

---

## 系统要求

### 最低配置

- **操作系统**: Ubuntu 20.04+, macOS 11+, Windows 10+ (WSL2)
- **Python**: 3.11 或更高版本
- **Node.js**: 18.x 或更高版本
- **内存**: 4GB RAM (推荐 8GB+)
- **磁盘**: 10GB 可用空间

### 推荐配置

- **操作系统**: Ubuntu 22.04+
- **Python**: 3.11+
- **Node.js**: 20.x+
- **内存**: 16GB RAM
- **磁盘**: 50GB+ SSD
- **网络**: 稳定的互联网连接

---

## 快速开始

### 1. 使用快速启动脚本（推荐）

```bash
# 克隆或进入项目目录
cd /home/cool/.openclaw-trading

# 运行快速启动脚本
./quick-start.sh start
```

这将自动：
- 创建 Python 虚拟环境
- 安装所有依赖
- 启动后端 API 服务
- 启动前端 UI 服务

### 2. 查看服务状态

```bash
./quick-start.sh status
```

### 3. 访问系统

- **前端界面**: http://localhost:3001
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

### 4. 停止服务

```bash
./quick-start.sh stop
```

### 5. 查看日志

```bash
# 查看后端日志
./quick-start.sh logs backend

# 查看前端日志
./quick-start.sh logs frontend
```

---

## 手动部署

### 步骤 1: 环境准备

#### 1.1 安装 Python 3.11

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-dev python3.11-venv python3-pip
```

**macOS (使用 Homebrew):**
```bash
brew install python@3.11
```

#### 1.2 安装 Node.js 和 npm

**Ubuntu/Debian:**
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

**macOS (使用 Homebrew):**
```bash
brew install node
```

#### 1.3 验证安装

```bash
python3.11 --version
node --version
npm --version
```

### 步骤 2: 项目设置

#### 2.1 克隆或进入项目目录

```bash
cd /home/cool/.openclaw-trading
```

#### 2.2 创建 Python 虚拟环境

```bash
python3.11 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 Windows: venv\Scripts\activate
```

#### 2.3 安装 Python 依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 2.4 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 步骤 3: 配置系统

#### 3.1 创建必要的目录

```bash
mkdir -p logs data/config data/backup data/models
```

#### 3.2 配置环境变量（可选）

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
nano .env
```

### 步骤 4: 启动服务

#### 4.1 启动后端服务（终端 1）

```bash
cd /home/cool/.openclaw-trading
source venv/bin/activate
python -m src.main
```

#### 4.2 启动前端服务（终端 2）

```bash
cd /home/cool/.openclaw-trading/frontend
npm run dev
```

---

## Docker部署

### 使用 Docker Compose（推荐）

#### 1. 准备 Docker Compose 配置

确保项目根目录有 `docker-compose.yml` 文件。

#### 2. 启动所有服务

```bash
cd /home/cool/.openclaw-trading
docker-compose up -d
```

#### 3. 查看服务状态

```bash
docker-compose ps
```

#### 4. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f frontend
```

#### 5. 停止服务

```bash
docker-compose down
```

### 构建自定义 Docker 镜像

#### 1. 构建后端镜像

```bash
docker build -t openclaw-trading:latest .
```

#### 2. 运行后端容器

```bash
docker run -d \
  --name openclaw-backend \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  openclaw-trading:latest
```

---

## 配置说明

### 主配置文件

配置文件位于 `data/config/default.yml`

```yaml
# API 服务器配置
api:
  host: "0.0.0.0"
  port: 8000
  enable_cors: true
  enable_swagger: true
  secret_key: "your-secret-key-here"
  access_token_expire_minutes: 30

# 控制器配置
controller:
  auto_restart_modules: true
  max_restart_attempts: 3
  health_check_interval: 30

# 大模型配置
llm:
  provider: "openai"  # openai, anthropic, local
  api_key: "your-api-key"
  model: "gpt-4"
  temperature: 0.7

# 策略配置
strategy:
  default_symbols: ["BTC/USDT", "ETH/USDT"]
  default_timeframe: "1h"
  risk_management:
    max_position_size: 0.1
    stop_loss: 0.02
    take_profit: 0.05
```

### 环境变量

可以通过环境变量覆盖配置：

```bash
# API 配置
export API_HOST=0.0.0.0
export API_PORT=8000

# 数据库配置
export DATABASE_URL=postgresql://user:pass@localhost:5432/trading

# 大模型配置
export LLM_PROVIDER=openai
export LLM_API_KEY=your-api-key
```

---

## 常见问题

### 1. 端口被占用

**问题**: `Address already in use` 错误

**解决方案**:
```bash
# 查找占用端口的进程
lsof -i :8000  # 后端端口
lsof -i :3001  # 前端端口

# 杀死进程
kill -9 <PID>
```

### 2. Python 依赖安装失败

**问题**: pip install 报错

**解决方案**:
```bash
# 升级 pip
pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 前端无法连接后端

**问题**: 前端显示网络错误

**解决方案**:
- 确认后端服务正在运行
- 检查 `frontend/vite.config.js` 中的代理配置
- 确认 CORS 设置正确

### 4. 数据库连接失败

**问题**: 无法连接到数据库

**解决方案**:
- 确认数据库服务正在运行
- 检查数据库连接字符串
- 确认数据库用户权限正确

### 5. 内存不足

**问题**: 系统运行缓慢或崩溃

**解决方案**:
- 增加系统内存
- 减少同时运行的策略数量
- 优化数据存储配置

---

## 生产环境部署建议

### 1. 使用进程管理器

**使用 systemd (Linux):**

```ini
# /etc/systemd/system/openclaw-trading.service
[Unit]
Description=OpenClaw Trading System
After=network.target

[Service]
Type=simple
User=trading
WorkingDirectory=/home/cool/.openclaw-trading
Environment="PATH=/home/cool/.openclaw-trading/venv/bin"
ExecStart=/home/cool/.openclaw-trading/venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务:
```bash
sudo systemctl enable openclaw-trading
sudo systemctl start openclaw-trading
sudo systemctl status openclaw-trading
```

### 2. 使用反向代理 (Nginx)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # 后端 API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 3. 设置 HTTPS (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 4. 数据备份

设置定期备份:
```bash
# 创建备份脚本
#!/bin/bash
BACKUP_DIR="/backup/trading"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/trading_$DATE.tar.gz /home/cool/.openclaw-trading/data
```

添加到 crontab:
```bash
# 每天凌晨 2 点备份
0 2 * * * /path/to/backup.sh
```

---

## 监控和维护

### 1. 健康检查

定期检查服务健康状态:
```bash
curl http://localhost:8000/health
```

### 2. 日志管理

- 后端日志: `logs/backend.log`
- 前端日志: `logs/frontend.log`
- 应用日志: `logs/app.log`

### 3. 性能监控

使用 Prometheus + Grafana 监控系统性能。

---

## 下一步

- 查看 [API文档.md](./API文档.md) 了解 API 接口
- 配置策略参数开始交易
- 设置风险控制规则
- 接入真实交易所 API

---

## 获取帮助

如遇到问题，请:
1. 查看日志文件
2. 检查系统要求
3. 参考常见问题部分
4. 提交 Issue 到项目仓库

---

**祝交易顺利！** 🚀
