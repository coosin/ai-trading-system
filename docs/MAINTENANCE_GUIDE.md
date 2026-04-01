# OpenClaw Trading System - 维护保养指南

**版本**: 1.0.0  
**创建日期**: 2026-04-01  
**适用对象**: OpenClaw 主智能体、运维工程师

---

## 📋 目录

1. [日常维护任务](#1-日常维护任务)
2. [周度维护任务](#2-周度维护任务)
3. [月度维护任务](#3-月度维护任务)
4. [故障排查指南](#4-故障排查指南)
5. [性能监控指标](#5-性能监控指标)
6. [应急处理流程](#6-应急处理流程)

---

## 1. 日常维护任务

### 1.1 每小时检查项

| 检查项 | 正常值 | 异常处理 |
|--------|--------|----------|
| 进程状态 | 运行中 | 重启服务 |
| 内存使用 | < 3Gi | 清理缓存或重启 |
| CPU 使用率 | < 50% | 检查异常进程 |
| 日志错误数 | 0 | 排查错误原因 |

### 1.2 检查命令

```bash
# 检查进程状态
ps aux | grep -E "python.*src.main" | grep -v grep

# 检查内存使用
free -h

# 检查磁盘空间
df -h /home

# 检查日志错误
tail -100 /home/cool/.openclaw-trading/logs/app.log | grep -E "(ERROR|CRITICAL)" | tail -20
```

### 1.3 自动化检查脚本

```bash
# 运行健康检查
curl -s http://localhost:8000/health
```

---

## 2. 周度维护任务

### 2.1 数据清理

| 任务 | 频率 | 说明 |
|------|------|------|
| 清理旧日志 | 每周 | 保留最近 7 天日志 |
| 清理临时文件 | 每周 | 删除 /tmp 下过期文件 |
| 压缩历史数据 | 每周 | 压缩超过 30 天的数据 |

### 2.2 清理脚本

```bash
# 清理 7 天前的日志
find /home/cool/.openclaw-trading/logs -name "*.log" -mtime +7 -delete

# 清理临时文件
find /tmp -name "openclaw-*" -mtime +1 -delete 2>/dev/null

# 清理记忆文件中的旧风险事件 (保留最近 7 天)
python3 -c "
import json
from datetime import datetime, timedelta

with open('/home/cool/.openclaw-trading/data/memory/enhanced_memory.json', 'r') as f:
    data = json.load(f)

cutoff = (datetime.now() - timedelta(days=7)).isoformat()
data['long_term'] = [m for m in data.get('long_term', []) 
    if m.get('category') != 'risk_event' or m.get('created_at', '') >= cutoff]

with open('/home/cool/.openclaw-trading/data/memory/enhanced_memory.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('清理完成')
"
```

### 2.3 系统备份

```bash
# 备份配置和数据
tar -czf /home/cool/.openclaw-trading/backups/backup_$(date +%Y%m%d).tar.gz \
    -C /home/cool/.openclaw-trading/data \
    -C /home/cool/.openclaw-trading/workspace \
    --exclude='*.log' \
    --exclude='__pycache__'
```

---

## 3. 月度维护任务

### 3.1 系统更新

- [ ] 检查并更新 Python 依赖包
- [ ] 检查并更新系统配置
- [ ] 审查系统日志，异常模式
- [ ] 优化数据库索引

### 3.2 性能优化

- [ ] 分析系统性能瓶颈
- [ ] 优化内存使用
- [ ] 清理无用代码和配置

### 3.3 安全检查

- [ ] 检查 API 密钥是否过期
- [ ] 审查访问日志
- [ ] 更新安全配置

---

## 4. 故障排查指南

### 4.1 常见问题

#### 问题 1: 系统无法启动

**症状**: 
- 进程立即退出
- 日志显示 "另一个实例已在运行中"

**排查步骤**:
```bash
# 1. 检查是否有其他实例运行
ps aux | grep "python.*src.main"

# 2. 检查锁文件
ls -la /tmp/openclaw-trading.lock /tmp/openclaw-trading.pid

# 3. 清理锁文件
rm -f /tmp/openclaw-trading.lock /tmp/openclaw-trading.pid

# 4. 重新启动
python3 -m src.main
```

#### 问题 2: LLM API 调用失败

**症状**:
- 日志显示 "OpenAI API调用失败"
- AI 分析无响应

**排查步骤**:
```bash
# 1. 检查模型配置
cat /home/cool/.openclaw-trading/data/config/default.yml | grep -A 20 "llm:"

# 2. 检查 API 连接
curl -v https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions

# 3. 检查日志
tail -50 /home/cool/.openclaw-trading/logs/app.log | grep -i "api"
```

#### 问题 3: 内存使用过高

**症状**:
- 磁盘空间不足
- 系统响应缓慢

**排查步骤**:
```bash
# 1. 检查内存使用
free -h

# 2. 检查大文件
du -sh /home/cool/.openclaw-trading/data/*/* | sort -h | tail -10

# 3. 清理记忆文件
python3 -c "
import json
with open('/home/cool/.openclaw-trading/data/memory/enhanced_memory.json', 'r') as f:
    data = json.load(f)
print(f'长期记忆数量: {len(data.get(\"long_term\", []))}')
"
```

### 4.2 紧急恢复流程

```bash
# 1. 停止服务
./scripts/stop-openclaw-trading.sh

# 2. 备份当前状态
tar -czf /home/cool/.openclaw-trading/backups/emergency_$(date +%Y%m%d_%H%M%S).tar.gz \
    /home/cool/.openclaw-trading/data \
    /home/cool/.openclaw-trading/logs

# 3. 清理锁文件
rm -f /tmp/openclaw-trading.*.lock /tmp/openclaw-trading.*.pid

# 4. 重启服务
./scripts/start-openclaw-trading.sh
```

---

## 5. 性能监控指标

### 5.1 关键指标

| 指标 | 正常范围 | 警告阈值 | 危险阈值 |
|------|----------|----------|----------|
| 内存使用 | < 2.5Gi | 2.5-3.5Gi | > 3.5Gi |
| CPU 使用率 | < 30% | 30-60% | > 60% |
| 磁盘使用 | < 70% | 70-85% | > 85% |
| 进程数 | 1 | 2-3 | > 3 |
| 日志错误/小时 | 0 | 1-5 | > 5 |

### 5.2 监控命令

```bash
# 实时监控
watch -n 1 "free -h | grep Mem"

# 进程监控
top -p $(pgrep -f "python.*src.main")

# 网络监控
netstat -an | grep 8000
```

---

## 6. 应急处理流程

### 6.1 服务宕机处理

```
1. 检查服务状态
   systemctl status openclaw-trading

2. 查看错误日志
   journalctl -u openclaw-trading -n 100

3. 重启服务
   systemctl restart openclaw-trading

4. 验证服务恢复
   curl http://localhost:8000/health
```

### 6.2 数据损坏处理

```
1. 停止服务
   systemctl stop openclaw-trading

2. 恢复最近备份
   tar -xzf /home/cool/.openclaw-trading/backups/backup_最新日期.tar.gz -C /

3. 验证数据完整性
   python3 -c "
import json
files = [
    '/home/cool/.openclaw-trading/data/memory/enhanced_memory.json',
    '/home/cool/.openclaw-trading/data/config/default.yml'
]
for f in files:
    try:
        with open(f) as fp:
            json.load(fp)
        print(f'✅ {f} OK')
    except Exception as e:
        print(f'❌ {f} ERROR: {e}')
"

4. 重启服务
   systemctl start openclaw-trading
```

---

## 📞 联系方式

- **技术支持**: 查看项目文档
- **紧急联系**: 检查系统日志获取详细错误信息

---

**文档版本**: 1.0.0  
**最后更新**: 2026-04-01
