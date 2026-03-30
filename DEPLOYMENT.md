# 全智能量化交易系统 - 部署文档

## 📋 系统概述

这是一个基于AI的全智能量化交易系统，支持：
- 多源数据融合分析
- 智能决策引擎
- 优化执行算法
- 全面风险监控
- 7x24h无人值守运行

## 🚀 快速开始

### 环境要求

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **磁盘空间** 至少50GB
- **内存** 至少8GB RAM
- **网络** 稳定的互联网连接

### 一键部署

```bash
# 1. 克隆或复制项目
cd /home/cool/.openclaw-trading

# 2. 设置环境变量
cp .env.example .env
# 编辑.env文件，设置必要的配置

# 3. 启动所有服务
docker-compose up -d

# 4. 查看服务状态
docker-compose ps

# 5. 查看日志
docker-compose logs -f ai-trader
```

### 访问地址

- **交易系统API**: http://localhost:8000
- **Grafana监控**: http://localhost:3000 (admin/admin123)
- **Kibana日志**: http://localhost:5601
- **Prometheus**: http://localhost:9090
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

## 🔧 详细配置

### 环境变量配置

编辑 `.env` 文件：

```bash
# 数据库配置
POSTGRES_PASSWORD=your_secure_password
POSTGRES_USER=trader
POSTGRES_DB=trading_db

# 监控配置
GRAFANA_PASSWORD=admin123
PROMETHEUS_PORT=9090

# 交易配置
TRADING_MODE=paper_trading  # paper_trading, live_trading, backtesting
API_KEY=your_api_key
API_SECRET=your_api_secret

# 网络配置
TIMEZONE=UTC
LOG_LEVEL=INFO
```

### 配置文件结构

```
config/
├── prometheus.yml          # Prometheus监控配置
├── alert_rules.yml         # 告警规则
├── nginx.conf             # Nginx反向代理配置
├── redis.conf             # Redis配置
├── logstash.conf          # Logstash日志处理配置
└── backup_script.sh       # 备份脚本
```

## 📊 监控和告警

### 监控指标

系统暴露以下指标给Prometheus：

1. **系统指标**
   - CPU/内存/磁盘使用率
   - 网络流量
   - 进程状态

2. **交易指标**
   - 订单提交/执行/取消数量
   - 执行延迟
   - 成交率

3. **风险指标**
   - 投资组合价值
   - 回撤率
   - 波动率
   - VaR/CVaR

4. **性能指标**
   - API延迟
   - 缓存命中率
   - 数据处理延迟

### 告警配置

告警规则位于 `config/alert_rules.yml`，包括：

- 系统资源告警（CPU/内存/磁盘）
- 交易异常告警（高错误率、执行延迟）
- 风险告警（高回撤、低流动性）
- 安全告警（未授权访问、合规违规）

## 🗄️ 数据管理

### 数据库

- **PostgreSQL**: 存储交易记录、配置、用户数据
- **Redis**: 缓存、会话、实时数据

### 数据备份

自动备份策略：

1. **每日备份**: 凌晨2点执行完整备份
2. **保留策略**: 
   - 完整备份：30天
   - 数据库备份：7天
   - 日志备份：14天

手动备份：
```bash
docker-compose exec backup /backup_script.sh
```

### 数据恢复

```bash
# 1. 停止服务
docker-compose down

# 2. 恢复数据
tar -xzf /backups/backup-YYYYMMDD-HHMMSS.tar.gz -C /

# 3. 启动服务
docker-compose up -d
```

## 🔒 安全和合规

### 安全配置

1. **网络隔离**: 所有服务在内部网络运行
2. **访问控制**: 
   - API密钥加密存储
   - 多因素认证支持
   - IP白名单
3. **数据加密**:
   - 传输层加密 (TLS)
   - 静态数据加密
   - 敏感信息脱敏

### 合规性检查

系统内置合规性检查：
- GDPR合规（数据匿名化、用户权利）
- PCI-DSS合规（支付数据保护）
- 内部合规标准

## 📈 性能优化

### 硬件建议

| 组件 | 最小配置 | 推荐配置 | 生产配置 |
|------|----------|----------|----------|
| CPU | 4核 | 8核 | 16核+ |
| 内存 | 8GB | 16GB | 32GB+ |
| 存储 | 50GB SSD | 200GB NVMe | 1TB NVMe RAID |
| 网络 | 100Mbps | 1Gbps | 10Gbps |

### 优化建议

1. **缓存优化**
   ```bash
   # 调整Redis内存策略
   redis-cli config set maxmemory 2gb
   redis-cli config set maxmemory-policy allkeys-lru
   ```

2. **数据库优化**
   ```sql
   -- 创建索引
   CREATE INDEX idx_trades_timestamp ON trades(timestamp);
   CREATE INDEX idx_orders_status ON orders(status);
   ```

3. **监控优化**
   - 调整Prometheus抓取间隔
   - 优化Grafana仪表板查询
   - 设置合理的告警阈值

## 🐛 故障排除

### 常见问题

1. **服务启动失败**
   ```bash
   # 查看日志
   docker-compose logs [service_name]
   
   # 检查端口冲突
   netstat -tulpn | grep :8000
   
   # 重新构建镜像
   docker-compose build --no-cache
   ```

2. **数据库连接问题**
   ```bash
   # 测试数据库连接
   docker-compose exec postgres pg_isready -U trader
   
   # 重置数据库
   docker-compose down -v
   docker-compose up -d
   ```

3. **监控数据缺失**
   ```bash
   # 检查Prometheus目标
   curl http://localhost:9090/api/v1/targets
   
   # 重启监控服务
   docker-compose restart prometheus grafana
   ```

### 日志查看

```bash
# 查看所有日志
docker-compose logs

# 查看特定服务日志
docker-compose logs ai-trader

# 实时日志
docker-compose logs -f

# 查看ELK日志
# 访问 http://localhost:5601
```

## 🔄 维护和升级

### 日常维护

1. **每日检查**
   ```bash
   # 检查服务状态
   docker-compose ps
   
   # 检查磁盘空间
   df -h
   
   # 检查日志错误
   grep -i error logs/app.log | tail -20
   ```

2. **每周维护**
   ```bash
   # 清理Docker资源
   docker system prune -f
   
   # 更新依赖
   docker-compose build --pull
   
   # 重启服务
   docker-compose restart
   ```

### 系统升级

1. **备份当前系统**
   ```bash
   docker-compose exec backup /backup_script.sh
   ```

2. **更新代码**
   ```bash
   git pull origin main
   ```

3. **重建和重启**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

4. **验证升级**
   ```bash
   # 检查服务状态
   docker-compose ps
   
   # 检查版本
   curl http://localhost:8000/health
   ```

## 📞 支持

### 获取帮助

1. **查看文档**
   - 本部署文档
   - 代码内文档字符串
   - API文档 (http://localhost:8000/docs)

2. **社区支持**
   - GitHub Issues
   - Discord社区
   - 技术论坛

3. **紧急联系**
   - 系统管理员
   - 技术支持团队

### 报告问题

请提供以下信息：
1. 问题描述
2. 复现步骤
3. 错误日志
4. 系统配置
5. 期望行为

## 📄 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 🎯 下一步

部署完成后，建议：

1. **测试系统**
   - 运行回测验证策略
   - 测试监控告警
   - 验证备份恢复

2. **生产准备**
   - 配置SSL证书
   - 设置生产环境变量
   - 进行压力测试

3. **持续优化**
   - 根据监控数据调整配置
   - 优化交易策略
   - 完善文档和自动化

---

**最后更新**: 2026-03-30  
**版本**: 1.0.0  
**作者**: AI Trading System Team