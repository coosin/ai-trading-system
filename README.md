# 🚀 全智能量化交易系统

基于人工智能的自动化量化交易系统，支持多交易所、多策略、实时风控和智能决策。

## ✨ 特性

- 🧠 **智能决策引擎**：融合技术分析、市场情绪、链上数据的多模型决策
- ⚡ **优化执行算法**：TWAP/VWAP/冰山订单等高级执行策略
- 🛡️ **全面风险控制**：实时风险监控和自动干预机制
- 📊 **企业级监控**：Prometheus + Grafana + ELK Stack 全方位监控
- 🔄 **持续学习优化**：从市场反馈中不断优化的学习能力
- 🐳 **容器化部署**：Docker + Docker Compose 一键部署

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Docker 20.10+
- Docker Compose 2.0+
- PostgreSQL 15+
- Redis 7+

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-org/ai-trading-system.git
cd ai-trading-system

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置必要的配置

# 5. 启动基础设施
docker-compose up -d postgres redis

# 6. 初始化数据库
alembic upgrade head

# 7. 运行开发服务器
python -m src.main
```

### 开发环境

```bash
# 运行测试
pytest

# 代码格式化
black src tests
isort src tests

# 代码检查
flake8 src tests
mypy src

# 生成依赖图
pipdeptree
```

## 📁 项目结构

```
ai-trading-system/
├── src/                    # 源代码
│   ├── modules/           # 核心模块
│   │   ├── core/         # 核心基础设施
│   │   ├── intelligence/ # 智能分析模块
│   │   ├── execution/    # 执行模块
│   │   ├── monitoring/   # 监控模块
│   │   └── testing/      # 测试模块
│   ├── api/              # API接口
│   ├── models/           # 数据模型
│   └── utils/            # 工具函数
├── tests/                # 测试代码
├── migrations/           # 数据库迁移
├── config/              # 配置文件
├── scripts/             # 运维脚本
├── logs/                # 日志文件
└── docs/                # 文档
```

## 🔧 配置说明

### 环境变量

主要环境变量配置在 `.env` 文件中：

```bash
# 数据库配置
DATABASE_URL=postgresql://trader:changeme123@localhost:5432/trading_db

# Redis配置
REDIS_URL=redis://localhost:6379/0

# 交易所API密钥
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# 监控配置
PROMETHEUS_PORT=9091
GRAFANA_PORT=3000

# 安全配置
SECRET_KEY=your_secret_key_here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### 配置文件

- `config/database.yml` - 数据库配置
- `config/redis.yml` - Redis配置
- `config/exchange.yml` - 交易所配置
- `config/risk.yml` - 风险控制配置
- `config/monitoring.yml` - 监控配置

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest -m unit

# 运行集成测试
pytest -m integration

# 运行E2E测试
pytest -m e2e

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

### 测试结构

```
tests/
├── unit/              # 单元测试
│   ├── core/         # 核心模块测试
│   ├── intelligence/ # 智能模块测试
│   └── execution/    # 执行模块测试
├── integration/      # 集成测试
│   ├── api/         # API测试
│   └── database/    # 数据库测试
└── e2e/             # 端到端测试
    └── trading/     # 交易流程测试
```

## 🐳 部署

### 开发环境

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 生产环境

```bash
# 使用生产配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 配置SSL证书
./scripts/setup-ssl.sh

# 配置监控告警
./scripts/setup-monitoring.sh
```

## 📊 监控和告警

### 访问地址

- **应用监控**: http://localhost:8000/metrics
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin123)
- **Kibana**: http://localhost:5601

### 默认告警规则

系统预配置了91个告警规则，包括：
- 系统资源监控（CPU、内存、磁盘）
- 交易性能监控（延迟、成功率、错误率）
- 风险指标监控（回撤、波动率、VaR）
- 业务指标监控（收益率、夏普比率、最大回撤）

## 🔒 安全

### 安全特性

- ✅ JWT身份认证和授权
- ✅ API密钥加密存储
- ✅ 输入验证和输出编码
- ✅ SQL注入防护
- ✅ XSS防护
- ✅ CSRF防护
- ✅ 速率限制
- ✅ 安全日志记录

### 安全扫描

```bash
# 扫描依赖漏洞
safety check

# 扫描代码安全问题
bandit -r src

# 扫描容器漏洞
trivy image ai-trading-system:latest
```

## 🤝 贡献

### 开发流程

1. **Fork 项目**
2. **创建功能分支** (`git checkout -b feature/amazing-feature`)
3. **提交更改** (`git commit -m 'feat: add amazing feature'`)
4. **推送到分支** (`git push origin feature/amazing-feature`)
5. **创建 Pull Request**

### 代码规范

- 使用 [Black](https://github.com/psf/black) 代码格式化
- 使用 [isort](https://github.com/PyCQA/isort) 导入排序
- 使用 [Flake8](https://flake8.pycqa.org/) 代码检查
- 使用 [MyPy](http://mypy-lang.org/) 类型检查
- 遵循 [Conventional Commits](https://www.conventionalcommits.org/) 提交规范

### 提交信息格式

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

**类型**:
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式化
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具更新

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 支持

- **GitHub Issues**: [问题报告](https://github.com/your-org/ai-trading-system/issues)
- **Discord**: [社区讨论](https://discord.gg/your-discord)
- **Email**: support@trading-system.com

## 🙏 致谢

感谢所有为这个项目做出贡献的开发者！

---

**版本**: 0.1.0  
**最后更新**: 2026-03-30  
**维护者**: AI Trading System Team