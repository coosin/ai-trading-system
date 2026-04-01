# OpenClaw Trading System - 维护保养指南

**版本**: 1.3.0  
**创建日期**: 2026-04-01  
**更新日期**: 2026-04-01  
**适用对象**: OpenClaw 主智能体、运维工程师

**核心运维原则**:
- ✅ **绝对不停止交易系统** - 保证交易连续性
- ✅ **优先在线修复** - 所有问题在线解决
- ✅ **重启是最后手段** - 仅在极端条件下考虑
- ✅ **7x24小时监控** - 确保系统稳定运行

**关键依赖说明**:
- 🔌 **代理服务**：交易系统关键依赖，影响所有API连接
- 📡 **必须确保代理稳定**：代理故障会导致交易中断
- 🛡️ **代理监控优先级高**：与交易系统进程同等重要

**系统端口说明**:
- **后端API服务端口**: 8000
- **前端开发服务器端口**: 5173  
- **代理服务端口**: 7890 (关键依赖，影响API连接)
- **监控检查端口**: 8000 (健康检查、API访问)

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
| 进程状态 | 运行中 | **在线监控并报警**，除非极端情况绝不停止 |
| 代理服务 | 运行中 | **立即检查修复**，代理故障会影响API连接 |
| 内存使用 | < 3Gi | **清理缓存、优化内存**，在线处理不重启 |
| CPU 使用率 | < 50% | 检查异常进程，**在线优化** |
| 日志错误数 | 0 | 排查错误原因，**在线修复** |

### 1.2 检查命令

```bash
# 检查进程状态
ps aux | grep -E "python.*src.main" | grep -v grep

# 检查代理服务状态（关键依赖）
curl --proxy http://127.0.0.1:7890 https://www.okx.com -I 2>/dev/null | head -1
# 或检查代理进程
ps aux | grep -E "(clash|v2ray|proxy)" | grep -v grep

# 检查内存使用
free -h

# 检查磁盘空间
df -h /home

# 检查日志错误
tail -100 /home/cool/.openclaw-trading/logs/app.log | grep -E "(ERROR|CRITICAL)" | tail -20
```

### 1.3 自动化检查脚本

```bash
# 运行后端健康检查（端口8000）
curl -s http://localhost:8000/health

# 检查代理服务连通性（关键依赖）
curl --proxy http://127.0.0.1:7890 https://www.okx.com -o /dev/null -w "代理状态: %{http_code}, 耗时: %{time_total}s\\n" 2>/dev/null || echo "❌ 代理连接失败"

# 检查前端开发服务器（端口5173）
curl -s http://localhost:5173 2>/dev/null | head -1

# 检查所有相关服务端口
netstat -tlnp | grep -E ":(8000|5173|7890)"
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

#### 问题 4: 代理服务故障

**症状**:
- 日志显示 "获取OKX真实行情失败"
- API调用超时或连接拒绝
- 交易系统无法获取市场数据

**排查步骤**:
```bash
# 1. 检查代理服务是否运行
ps aux | grep -E "(clash|v2ray|proxy|7890)" | grep -v grep

# 2. 测试代理连通性
curl --proxy http://127.0.0.1:7890 https://www.okx.com -I 2>/dev/null | head -1

# 3. 检查代理配置
env | grep -i proxy
cat ~/.bashrc ~/.zshrc 2>/dev/null | grep -i proxy

# 4. 检查网络连接
ping -c 3 www.okx.com
curl -v https://www.okx.com 2>&1 | head -20

# 5. 重启代理服务（在线操作，不影响交易系统）
# sudo systemctl restart clash  # 根据实际代理软件调整
# 或
# pkill -f "clash" && nohup clash > /tmp/clash.log 2>&1 &

# 6. 验证修复
sleep 2 && curl --proxy http://127.0.0.1:7890 https://www.okx.com -o /dev/null -w "修复后: %{http_code}\\n"
```

### 4.2 在线应急处理流程

**基本原则：绝不停止交易系统，保证交易连续性**

```bash
# 1. 立即报警通知
#    发送紧急通知给管理员，说明问题情况

# 2. 在线创建紧急备份（不停止服务）
tar -czf /home/cool/.openclaw-trading/backups/emergency_$(date +%Y%m%d_%H%M%S).tar.gz \
    /home/cool/.openclaw-trading/data \
    /home/cool/.openclaw-trading/logs \
    --exclude='*.lock'

# 3. 在线诊断和修复
#    - 检查进程状态（不停止）
#    - 分析错误日志（不中断）
#    - 在线修复配置（热更新）
#    - 清理无效锁文件（谨慎操作）

# 4. 如需极端情况处理（仅在无法联系管理员且系统完全失控时）
#    a. 选择市场低波动时段
#    b. 极速重启（秒级完成）
#    c. 确保仓位状态恢复
#    d. 立即报告处理情况

# 注意：优先在线修复，重启是最后手段
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
# 监控后端API服务端口（8000）和前端开发端口（5173）
netstat -an | grep -E ":(8000|5173)"
```

---

## 6. 应急处理流程

### 6.1 服务异常在线处理

**核心原则：服务必须保持运行，交易不能中断**

```
1. 立即报警通知
   # 发送紧急通知，说明异常情况

2. 在线诊断问题（不停止服务）
   # 检查进程状态（ps aux | grep python.*src.main）
   # 查看实时错误日志（tail -f /home/cool/.openclaw-trading/logs/app.log）
   # 监控系统资源（top -p <pid>）

3. 在线修复方案（优先级排序）
   a. 热更新配置（在线加载新配置）
   b. 重启单个异常模块（不停止主进程）
   c. 内存优化和垃圾回收（在线执行）
   d. 网络连接修复（代理、API重连）

4. 极端情况处理（最后手段）
   # 仅在以下条件同时满足时考虑：
   # 1. 系统完全失控，无法正常交易
   # 2. 无法联系到管理员决策
   # 3. 选择市场最低波动时段
   # 4. 执行极速重启（< 5秒完成）
   
   如果必须重启：
   a. 创建完整状态快照
   b. 极速重启服务
   c. 验证所有仓位状态恢复
   d. 立即报告处理结果

5. 验证服务恢复（在线验证）
   curl -s http://localhost:8000/health
   # 持续监控确保交易正常进行
```

### 6.2 在线数据修复处理

**核心原则：交易继续运行，在线修复数据问题**

```
1. 立即报警通知
   # 发送数据异常警告，保持交易运行

2. 在线诊断数据问题（不停止服务）
   # 检查关键数据文件完整性
   python3 -c "
import json
files = [
    '/home/cool/.openclaw-trading/data/memory/enhanced_memory.json',
    '/home/cool/.openclaw-trading/data/config/default.yml'
]
errors = []
for f in files:
    try:
        with open(f) as fp:
            json.load(fp)
        print(f'✅ {f} OK')
    except Exception as e:
        errors.append((f, str(e)))
        print(f'❌ {f} ERROR: {e}')
        
if errors:
    print('\\n发现数据问题，开始在线修复...')
"

3. 在线数据修复策略
   a. 配置文件损坏 → 在线热重载配置
   b. 记忆文件损坏 → 使用备份副本在线替换
   c. 交易数据异常 → 在线校验和修复
   d. 日志文件问题 → 在线清理和重建

4. 在线恢复数据（不停止交易）
   # 对于非关键数据：在线修复
   # 对于关键配置文件：在线热更新
   # 对于交易状态数据：在线验证和校正
   
   # 示例：在线修复记忆文件
   python3 -c "
import json, shutil, os
backup_file = '/home/cool/.openclaw-trading/backups/latest_memory_backup.json'
current_file = '/home/cool/.openclaw-trading/data/memory/enhanced_memory.json'

try:
    # 尝试修复当前文件
    with open(current_file, 'r') as f:
        data = json.load(f)
    print('✅ 当前记忆文件可读取')
except:
    print('⚠️ 当前记忆文件损坏，尝试在线恢复...')
    if os.path.exists(backup_file):
        shutil.copy2(backup_file, current_file)
        print('✅ 已在线恢复记忆文件（交易继续运行）')
    else:
        print('⚠️ 无可用备份，创建空记忆结构（交易继续运行）')
        with open(current_file, 'w') as f:
            json.dump({'short_term': [], 'long_term': []}, f)
"

5. 验证修复结果（在线验证）
   # 验证数据完整性，确保交易正常
   curl -s http://localhost:8000/health
   # 监控交易系统是否正常处理订单

注意：绝不停止交易系统进行数据修复，所有操作在线完成。
```

---

## 📞 联系方式

- **技术支持**: 查看项目文档
- **紧急联系**: 检查系统日志获取详细错误信息

---

**文档版本**: 1.0.0  
**最后更新**: 2026-04-01
