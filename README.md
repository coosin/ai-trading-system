# OpenClaw Trading - 全智能量化交易系统

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

**一个完全自动化、AI驱动的加密货币量化交易系统**

[快速开始](#快速开始) • [功能特性](#功能特性) • [系统架构](#系统架构) • [部署指南](docs/DEPLOYMENT.md) • [API文档](docs/API.md)

</div>

---

## 📖 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [使用指南](#使用指南)
- [开发指南](#开发指南)
- [安全建议](#安全建议)
- [风险提示](#风险提示)
- [常见问题](#常见问题)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 项目简介

OpenClaw Trading 是一个**完全自动化**的AI驱动量化交易系统，专为加密货币市场设计。系统集成了先进的AI模型、实时市场分析、智能风险管理和自我学习能力，能够实现从数据采集到交易执行的全流程自动化，无需人工干预。

### 🎯 设计目标

- **全智能自动化**: 从数据采集到交易执行完全自动化
- **AI驱动决策**: 使用大语言模型进行市场分析和交易决策
- **风险可控**: 多层次风险管理和实时监控
- **持续学习**: 从交易经验中学习并优化策略
- **易于扩展**: 模块化设计，支持插件和策略扩展

### 📊 系统状态

| 模块 | 状态 | 自动化程度 |
|------|------|-----------|
| 数据采集 | ✅ 正常 | 100% |
| AI分析 | ✅ 正常 | 100% |
| 交易执行 | ✅ 正常 | 100% |
| 风险管理 | ✅ 正常 | 100% |
| 自我学习 | ✅ 正常 | 100% |

---

## 核心特性

### 🤖 AI智能引擎

- **多模型支持**: 支持讯飞、OpenAI、Anthropic、Google等多种AI模型
- **智能市场分析**: 深度分析市场趋势、技术指标、情绪指标
- **自主决策生成**: AI自动生成交易信号和策略
- **上下文记忆**: 记住历史交易、用户偏好和市场规律

### 📈 全自动交易

- **多时间框架分析**: 支持1m、5m、15m、1h、4h、1d多周期分析
- **实时数据采集**: 自动采集K线、订单簿、账户数据
- **智能订单执行**: 自动下单、监控、止损止盈
- **多交易对支持**: 支持BTC、ETH、SOL、BNB等主流币种

### 🛡️ 风险管理

- **账户级风险控制**: 最大回撤、杠杆限制、保证金监控
- **仓位级风险控制**: 单笔风险、持仓限制、相关性控制
- **实时风险监控**: 10秒一次的风险扫描和预警
- **自动止损止盈**: 智能设置和执行止损止盈

### 🧠 自我学习

- **经验总结**: 自动总结成功和失败的交易模式
- **策略优化**: 基于历史表现自动优化策略参数
- **模式识别**: 识别市场规律和交易机会
- **持续进化**: 不断学习和适应市场变化

### 📊 监控与通知

- **实时监控**: 系统状态、交易表现、风险指标
- **多渠道通知**: Telegram、邮件、Webhook
- **详细日志**: 完整的操作日志和错误追踪
- **可视化界面**: Web界面和API接口

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenClaw Trading                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  数据采集层   │  │  AI分析层    │  │  交易执行层   │      │
│  │              │  │              │  │              │      │
│  │ • K线数据    │  │ • 市场分析   │  │ • 订单管理   │      │
│  │ • 订单簿     │  │ • 信号生成   │  │ • 仓位管理   │      │
│  │ • 账户数据   │  │ • 策略优化   │  │ • 止损止盈   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  风险管理层   │  │  学习引擎    │  │  监控通知层   │      │
│  │              │  │              │  │              │      │
│  │ • 风险评估   │  │ • 经验总结   │  │ • 状态监控   │      │
│  │ • 仓位控制   │  │ • 模式识别   │  │ • 告警通知   │      │
│  │ • 预警机制   │  │ • 策略优化   │  │ • 日志记录   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

详细架构请参考 [系统架构文档](docs/ARCHITECTURE.md)

---

## 快速开始

### 前置要求

- Python 3.8+
- pip 包管理器
- 交易所API密钥 (OKX推荐)
- AI模型API密钥 (讯飞推荐)

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/your-username/openclaw-trading.git
cd openclaw-trading
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置环境变量**

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，填写必需的API密钥
nano .env
```

**必需配置项:**

```bash
# AI模型配置 (必需)
XUNFEI_API_KEY=your_xunfei_api_key_here

# 交易所配置 (必需)
OKX_API_KEY=your_okx_api_key_here
OKX_SECRET=your_okx_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here

# 通知配置 (可选)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

4. **启动系统**

```bash
python start.py
```

### 验证安装

访问 http://localhost:8000/docs 查看API文档和系统状态

---

## 配置说明

### 主配置文件

系统使用 `config/config.yaml` 作为主配置文件，支持以下配置:

- **系统配置**: 运行模式、日志级别、调试选项
- **AI模型配置**: 模型选择、参数调优、任务映射
- **交易配置**: 交易对、分析间隔、风险参数
- **风险管理**: 止损止盈、仓位限制、风险阈值
- **交易所配置**: API密钥、代理设置、超时配置
- **监控配置**: 告警渠道、通知规则、日志管理

详细配置说明请参考 [配置文档](docs/CONFIGURATION.md)

### 环境变量

系统支持通过环境变量覆盖配置，优先级为:

**系统环境变量 > .env文件 > config.yaml默认值**

完整的环境变量列表请参考 [.env.example](.env.example)

---

## 使用指南

### 基本使用

1. **启动系统**

```bash
python start.py
```

2. **查看系统状态**

访问 http://localhost:8000/api/status

3. **监控交易**

查看 `logs/trading.log` 文件或通过Telegram接收通知

4. **停止系统**

按 `Ctrl+C` 安全停止系统

### 高级功能

- **策略自定义**: 在 `src/modules/strategies/` 目录添加自定义策略
- **插件开发**: 参考 [插件开发指南](docs/PLUGIN_DEVELOPMENT.md)
- **API调用**: 使用REST API进行程序化控制

详细使用指南请参考 [用户手册](docs/USER_GUIDE.md)

---

## 开发指南

### 项目结构

```
openclaw-trading/
├── config/              # 配置文件
│   └── config.yaml     # 主配置文件
├── src/                # 源代码
│   ├── modules/        # 功能模块
│   │   ├── core/      # 核心模块
│   │   ├── data/      # 数据模块
│   │   ├── strategies/ # 策略模块
│   │   ├── exchanges/  # 交易所接口
│   │   └── api/       # API接口
│   └── utils/         # 工具函数
├── workspace/          # AI记忆文件
├── data/              # 数据存储
├── logs/              # 日志文件
├── tests/             # 测试文件
├── docs/              # 文档
├── .env.example       # 环境变量模板
├── requirements.txt   # 依赖列表
└── start.py          # 启动脚本
```

### 开发环境设置

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest tests/

# 代码格式化
black src/

# 代码检查
flake8 src/
```

详细开发指南请参考 [开发文档](DEVELOPMENT.md)

---

## 安全建议

### ⚠️ 重要安全提示

1. **API密钥安全**
   - ❌ 不要提交.env文件到版本控制
   - ✅ 使用环境变量存储敏感信息
   - ✅ 定期轮换API密钥
   - ✅ 限制API密钥权限

2. **资金安全**
   - ✅ 先在模拟环境测试
   - ✅ 使用小额资金起步
   - ✅ 设置合理的止损
   - ✅ 监控账户余额

3. **系统安全**
   - ✅ 使用防火墙限制访问
   - ✅ 定期更新依赖
   - ✅ 监控系统日志
   - ✅ 备份重要数据

---

## 风险提示

### ⚠️ 投资风险警告

**加密货币交易存在极高风险，可能导致本金全部损失！**

- 市场风险: 加密货币价格波动剧烈
- 技术风险: 系统可能存在bug或故障
- AI风险: AI模型可能产生错误决策
- 流动性风险: 市场流动性不足可能导致无法成交
- 监管风险: 政策变化可能影响交易

**使用本系统即表示您已了解并接受上述风险！**

---

## 常见问题

### Q: 系统支持哪些交易所？
A: 目前主要支持OKX交易所，未来将支持更多交易所。

### Q: 需要多少资金才能开始？
A: 建议至少100 USDT起步，但强烈建议先在模拟环境测试。

### Q: AI模型如何选择？
A: 默认使用讯飞astron-code-latest模型，也支持OpenAI、Anthropic等模型。

### Q: 系统是否需要人工干预？
A: 系统设计为全自动化，但建议定期监控和调整参数。

### Q: 如何提高交易成功率？
A: 建议优化风险参数、选择合适的交易对、监控市场变化。

更多问题请参考 [FAQ文档](docs/FAQ.md) 或提交 [Issue](https://github.com/your-username/openclaw-trading/issues)

---

## 贡献指南

我们欢迎所有形式的贡献！

### 贡献方式

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 贡献指南

- 遵循代码规范
- 添加必要的测试
- 更新相关文档
- 保持提交历史清晰

详细指南请参考 [贡献指南](CONTRIBUTING.md)

---

## 更新日志

### v1.0.0 (2026-04-02)

**新增功能:**
- ✅ 全智能AI交易引擎
- ✅ 多模型支持和管理
- ✅ 完整的风险管理系统
- ✅ AI自我学习引擎
- ✅ 多渠道通知系统

**优化改进:**
- ✅ 移除硬编码API密钥，提升安全性
- ✅ 规范化配置管理
- ✅ 完善错误处理和日志
- ✅ 优化项目结构

**已知问题:**
- ⚠️ 多源数据融合需要外部数据源支持
- ⚠️ 部分高级策略需要进一步测试

完整更新日志请参考 [CHANGELOG.md](docs/CHANGELOG.md)

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 联系方式

- 项目主页: https://github.com/your-username/openclaw-trading
- 问题反馈: https://github.com/your-username/openclaw-trading/issues
- 邮箱: your-email@example.com

---

## 致谢

感谢所有贡献者和开源项目的支持！

- [ccxt](https://github.com/ccxt/ccxt) - 加密货币交易库
- [FastAPI](https://fastapi.tiangolo.com/) - 现代Web框架
- [aiohttp](https://docs.aiohttp.org/) - 异步HTTP客户端

---

<div align="center">

**⭐ 如果这个项目对您有帮助，请给一个Star支持！⭐**

Made with ❤️ by OpenClaw Team

</div>
