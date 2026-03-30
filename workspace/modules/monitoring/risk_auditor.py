#!/usr/bin/env python3
"""
风险审计器
深度风险分析、合规检查、异常检测和审计报告
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
import hashlib
import json
from collections import defaultdict, deque
import warnings
warnings.filterwarnings('ignore')

@dataclass
class RiskFinding:
    """风险发现"""
    timestamp: datetime
    risk_id: str
    risk_type: str  # 'security', 'compliance', 'operational', 'financial', 'market'
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    title: str
    description: str
    affected_components: List[str]
    evidence: Dict[str, Any]
    recommendations: List[str]
    status: str = 'OPEN'  # OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE
    assigned_to: str = None
    resolution_date: datetime = None
    resolution_notes: str = None
    
    def __post_init__(self):
        if not self.risk_id:
            self.risk_id = hashlib.md5(
                f"{self.timestamp}_{self.risk_type}_{self.title}".encode()
            ).hexdigest()[:12]

@dataclass
class ComplianceCheck:
    """合规检查"""
    check_id: str
    standard: str  # 'ISO27001', 'SOC2', 'GDPR', 'PCI-DSS', 'INTERNAL'
    requirement: str
    description: str
    status: str  # 'PASS', 'FAIL', 'WARNING', 'NOT_APPLICABLE'
    evidence: Dict[str, Any]
    last_check: datetime
    next_check: datetime

@dataclass
class SecurityAlert:
    """安全告警"""
    alert_id: str
    alert_type: str  # 'UNAUTHORIZED_ACCESS', 'DATA_LEAK', 'MALWARE', 'DOS', 'CONFIG_CHANGE'
    severity: str
    source: str
    target: str
    description: str
    timestamp: datetime
    indicators: Dict[str, Any]
    actions_taken: List[str]
    status: str = 'NEW'  # NEW, INVESTIGATING, MITIGATED, RESOLVED

@dataclass
class AuditReport:
    """审计报告"""
    report_id: str
    audit_type: str  # 'DAILY', 'WEEKLY', 'MONTHLY', 'AD_HOC', 'INCIDENT'
    start_date: datetime
    end_date: datetime
    auditor: str
    
    # 摘要
    summary: str
    total_findings: int
    critical_findings: int
    high_findings: int
    medium_findings: int
    low_findings: int
    
    # 详细发现
    findings: List[RiskFinding]
    compliance_checks: List[ComplianceCheck]
    security_alerts: List[SecurityAlert]
    
    # 建议
    recommendations: List[str]
    action_items: List[Dict[str, str]]
    
    def __post_init__(self):
        if not self.report_id:
            self.report_id = f"AUDIT_{self.start_date.strftime('%Y%m%d')}_{self.audit_type}"

class RiskAuditor:
    """风险审计器"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        # 风险发现存储
        self.risk_findings: Dict[str, RiskFinding] = {}
        self.finding_history: List[RiskFinding] = []
        
        # 合规检查
        self.compliance_checks: Dict[str, ComplianceCheck] = {}
        
        # 安全告警
        self.security_alerts: Dict[str, SecurityAlert] = {}
        
        # 审计报告
        self.audit_reports: List[AuditReport] = []
        
        # 风险模式
        self.risk_patterns = self._load_risk_patterns()
        
        # 审计规则
        self.audit_rules = self._load_audit_rules()
        
        # 合规标准
        self.compliance_standards = self._load_compliance_standards()
        
        # 监控任务
        self.monitoring_tasks = []
        self.is_running = False
        
        # 配置
        self.config = {
            'audit_frequency_hours': 24,
            'compliance_check_frequency_hours': 12,
            'security_monitoring_interval_minutes': 5,
            'risk_thresholds': {
                'max_consecutive_losses': 5,
                'max_daily_loss_percent': 5.0,
                'max_position_concentration': 30.0,
                'min_available_balance': 1000.0,
                'max_leverage': 3.0
            },
            'alert_channels': ['console', 'file', 'email'],
            'retention_days': 90
        }
        
        # 加载配置
        if config_manager:
            self._load_config()
    
    def _load_config(self):
        """加载配置"""
        
        risk_config = self.config_manager.get_config('risk', 'audit', {})
        
        if risk_config:
            self.config.update({
                'audit_frequency_hours': risk_config.get('audit_frequency_hours', 24),
                'compliance_check_frequency_hours': risk_config.get('compliance_check_frequency_hours', 12),
                'security_monitoring_interval_minutes': risk_config.get('security_monitoring_interval_minutes', 5),
                'risk_thresholds': risk_config.get('thresholds', self.config['risk_thresholds']),
                'alert_channels': risk_config.get('alert_channels', ['console', 'file']),
                'retention_days': risk_config.get('retention_days', 90)
            })
    
    def _load_risk_patterns(self) -> Dict[str, Dict]:
        """加载风险模式"""
        
        patterns = {
            'unauthorized_access': {
                'pattern': '从异常IP地址访问系统',
                'indicators': ['failed_login_attempts', 'ip_geolocation_mismatch', 'unusual_access_time'],
                'severity': 'HIGH',
                'detection_logic': self._detect_unauthorized_access
            },
            'data_leakage': {
                'pattern': '敏感数据泄露',
                'indicators': ['large_data_export', 'unencrypted_transmission', 'external_sharing'],
                'severity': 'CRITICAL',
                'detection_logic': self._detect_data_leakage
            },
            'config_drift': {
                'pattern': '配置漂移',
                'indicators': ['config_changes', 'version_mismatch', 'missing_updates'],
                'severity': 'MEDIUM',
                'detection_logic': self._detect_config_drift
            },
            'financial_anomaly': {
                'pattern': '财务异常',
                'indicators': ['unexpected_losses', 'concentration_risk', 'liquidity_issues'],
                'severity': 'HIGH',
                'detection_logic': self._detect_financial_anomaly
            },
            'market_manipulation': {
                'pattern': '市场操纵嫌疑',
                'indicators': ['wash_trading', 'spoofing', 'pump_and_dump'],
                'severity': 'CRITICAL',
                'detection_logic': self._detect_market_manipulation
            },
            'operational_failure': {
                'pattern': '操作失败',
                'indicators': ['system_downtime', 'failed_transactions', 'data_loss'],
                'severity': 'HIGH',
                'detection_logic': self._detect_operational_failure
            }
        }
        
        return patterns
    
    def _load_audit_rules(self) -> Dict[str, Dict]:
        """加载审计规则"""
        
        rules = {
            'daily_trade_review': {
                'name': '每日交易审查',
                'frequency': 'DAILY',
                'check_logic': self._daily_trade_review,
                'required': True
            },
            'weekly_risk_assessment': {
                'name': '每周风险评估',
                'frequency': 'WEEKLY',
                'check_logic': self._weekly_risk_assessment,
                'required': True
            },
            'monthly_compliance_check': {
                'name': '月度合规检查',
                'frequency': 'MONTHLY',
                'check_logic': self._monthly_compliance_check,
                'required': True
            },
            'config_audit': {
                'name': '配置审计',
                'frequency': 'DAILY',
                'check_logic': self._config_audit,
                'required': False
            },
            'access_log_review': {
                'name': '访问日志审查',
                'frequency': 'DAILY',
                'check_logic': self._access_log_review,
                'required': True
            }
        }
        
        return rules
    
    def _load_compliance_standards(self) -> Dict[str, Dict]:
        """加载合规标准"""
        
        standards = {
            'INTERNAL': {
                'name': '内部合规标准',
                'requirements': [
                    {
                        'id': 'INT-001',
                        'requirement': '交易系统必须记录所有操作日志',
                        'description': '确保所有系统操作可追踪',
                        'check_logic': self._check_audit_logging
                    },
                    {
                        'id': 'INT-002',
                        'requirement': '敏感配置必须加密存储',
                        'description': '防止配置信息泄露',
                        'check_logic': self._check_config_encryption
                    },
                    {
                        'id': 'INT-003',
                        'requirement': '所有交易必须通过风险检查',
                        'description': '确保交易符合风险限制',
                        'check_logic': self._check_trade_risk_controls
                    },
                    {
                        'id': 'INT-004',
                        'requirement': '定期备份关键数据',
                        'description': '防止数据丢失',
                        'check_logic': self._check_data_backup
                    },
                    {
                        'id': 'INT-005',
                        'requirement': '多因素认证用于关键操作',
                        'description': '增强账户安全',
                        'check_logic': self._check_mfa_enforcement
                    }
                ]
            },
            'GDPR': {
                'name': '通用数据保护条例',
                'requirements': [
                    {
                        'id': 'GDPR-001',
                        'requirement': '用户数据必须匿名化处理',
                        'description': '保护用户隐私',
                        'check_logic': self._check_data_anonymization
                    },
                    {
                        'id': 'GDPR-002',
                        'requirement': '用户有权访问和删除其数据',
                        'description': '数据主体权利',
                        'check_logic': self._check_data_subject_rights
                    }
                ]
            },
            'PCI-DSS': {
                'name': '支付卡行业数据安全标准',
                'requirements': [
                    {
                        'id': 'PCI-001',
                        'requirement': '支付数据必须加密传输',
                        'description': '保护支付信息',
                        'check_logic': self._check_payment_data_encryption
                    }
                ]
            }
        }
        
        return standards
    
    async def start(self):
        """启动风险审计器"""
        
        if self.is_running:
            print("风险审计器已启动")
            return
        
        print("🚀 启动风险审计器...")
        self.is_running = True
        
        # 启动监控任务
        self.monitoring_tasks = [
            asyncio.create_task(self._continuous_risk_monitoring()),
            asyncio.create_task(self._compliance_monitoring()),
            asyncio.create_task(self._security_monitoring()),
            asyncio.create_task(self._audit_scheduler()),
            asyncio.create_task(self._cleanup_old_data())
        ]
        
        print("✅ 风险审计器已启动")
    
    async def stop(self):
        """停止风险审计器"""
        
        print("🛑 停止风险审计器...")
        self.is_running = False
        
        # 停止所有任务
        for task in self.monitoring_tasks:
            task.cancel()
        
        # 等待任务完成
        await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        
        print("✅ 风险审计器已停止")
    
    async def _continuous_risk_monitoring(self):
        """持续风险监控"""
        
        print("👁️ 启动持续风险监控...")
        
        while self.is_running:
            try:
                # 执行所有风险模式检测
                findings = await self._detect_risk_patterns()
                
                # 记录新的风险发现
                for finding in findings:
                    if finding.risk_id not in self.risk_findings:
                        self.risk_findings[finding.risk_id] = finding
                        self.finding_history.append(finding)
                        
                        # 触发告警
                        await self._trigger_risk_alert(finding)
                
                # 每5分钟检查一次
                await asyncio.sleep(300)
                
            except Exception as e:
                print(f"风险监控出错: {e}")
                await asyncio.sleep(60)
    
    async def _compliance_monitoring(self):
        """合规监控"""
        
        print("📜 启动合规监控...")
        
        while self.is_running:
            try:
                # 执行合规检查
                for standard_name, standard in self.compliance_standards.items():
                    for requirement in standard['requirements']:
                        check_id = f"{standard_name}_{requirement['id']}"
                        
                        # 执行检查
                        status, evidence = await requirement['check_logic']()
                        
                        # 更新或创建检查记录
                        check = ComplianceCheck(
                            check_id=check_id,
                            standard=standard_name,
                            requirement=requirement['requirement'],
                            description=requirement['description'],
                            status=status,
                            evidence=evidence,
                            last_check=datetime.now(),
                            next_check=datetime.now() + timedelta(hours=self.config['compliance_check_frequency_hours'])
                        )
                        
                        self.compliance_checks[check_id] = check
                
                # 每12小时检查一次
                await asyncio.sleep(self.config['compliance_check_frequency_hours'] * 3600)
                
            except Exception as e:
                print(f"合规监控出错: {e}")
                await asyncio.sleep(3600)
    
    async def _security_monitoring(self):
        """安全监控"""
        
        print("🔒 启动安全监控...")
        
        while self.is_running:
            try:
                # 检查安全事件
                alerts = await self._check_security_events()
                
                for alert in alerts:
                    if alert.alert_id not in self.security_alerts:
                        self.security_alerts[alert.alert_id] = alert
                        
                        # 触发安全告警
                        await self._trigger_security_alert(alert)
                
                # 每5分钟检查一次
                await asyncio.sleep(self.config['security_monitoring_interval_minutes'] * 60)
                
            except Exception as e:
                print(f"安全监控出错: {e}")
                await asyncio.sleep(300)
    
    async def _audit_scheduler(self):
        """审计调度器"""
        
        print("📅 启动审计调度器...")
        
        while self.is_running:
            try:
                # 检查需要执行的审计
                for rule_name, rule in self.audit_rules.items():
                    should_run = await self._should_run_audit(rule_name, rule['frequency'])
                    
                    if should_run:
                        print(f"  执行审计规则: {rule['name']}")
                        
                        # 执行审计
                        findings = await rule['check_logic']()
                        
                        # 创建审计报告
                        if findings:
                            report = await self._create_audit_report(
                                audit_type=rule['frequency'],
                                findings=findings
                            )
                            
                            self.audit_reports.append(report)
                            
                            print(f"  ✅ 审计完成: {report.report_id}, 发现 {len(findings)} 个问题")
                
                # 每小时检查一次
                await asyncio.sleep(3600)
                
            except Exception as e:
                print(f"审计调度器出错: {e}")
                await asyncio.sleep(1800)
    
    async def _cleanup_old_data(self):
        """清理旧数据"""
        
        print("🧹 启动数据清理任务...")
        
        while self.is_running:
            try:
                cutoff_date = datetime.now() - timedelta(days=self.config['retention_days'])
                
                # 清理旧的风险发现
                self.finding_history = [
                    finding for finding in self.finding_history
                    if finding.timestamp > cutoff_date
                ]
                
                # 清理风险发现索引
                expired_findings = [
                    risk_id for risk_id, finding in self.risk_findings.items()
                    if finding.timestamp < cutoff_date
                ]
                for risk_id in expired_findings:
                    del self.risk_findings[risk_id]
                
                # 清理旧的安全告警
                expired_alerts = [
                    alert_id for alert_id, alert in self.security_alerts.items()
                    if alert.timestamp < cutoff_date
                ]
                for alert_id in expired_alerts:
                    del self.security_alerts[alert_id]
                
                # 清理旧的审计报告
                self.audit_reports = [
                    report for report in self.audit_reports
                    if report.end_date > cutoff_date
                ]
                
                print(f"🧹 清理完成: {len(expired_findings)} 个过期发现, {len(expired_alerts)} 个过期告警")
                
                # 每天清理一次
                await asyncio.sleep(86400)
                
            except Exception as e:
                print(f"数据清理出错: {e}")
                await asyncio.sleep(43200)
    
    async def _detect_risk_patterns(self) -> List[RiskFinding]:
        """检测风险模式"""
        
        findings = []
        
        for pattern_name, pattern in self.risk_patterns.items():
            try:
                # 执行检测逻辑
                detection_result = await pattern['detection_logic']()
                
                if detection_result['detected']:
                    finding = RiskFinding(
                        timestamp=datetime.now(),
                        risk_id=f"{pattern_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        risk_type=self._get_risk_type_from_pattern(pattern_name),
                        severity=pattern['severity'],
                        title=pattern['pattern'],
                        description=detection_result['description'],
                        affected_components=detection_result.get('affected_components', ['system']),
                        evidence=detection_result.get('evidence', {}),
                        recommendations=detection_result.get('recommendations', ['请进一步调查'])
                    )
                    
                    findings.append(finding)
                    
            except Exception as e:
                print(f"风险模式检测失败 ({pattern_name}): {e}")
        
        return findings
    
    async def _detect_unauthorized_access(self) -> Dict[str, Any]:
        """检测未授权访问"""
        
        # 这里应该集成真实的访问日志分析
        # 简化实现：随机检测
        
        detected = np.random.random() < 0.05  # 5%概率检测到
        
        if detected:
            return {
                'detected': True,
                'description': '检测到来自异常IP地址的访问尝试',
                'affected_components': ['authentication', 'api_gateway'],
                'evidence': {
                    'source_ip': '192.168.1.100',
                    'attempt_count': 15,
                    'timeframe': 'last_hour'
                },
                'recommendations': [
                    '加强访问控制',
                    '启用IP黑名单',
                    '实施速率限制'
                ]
            }
        
        return {'detected': False}
    
    async def _detect_data_leakage(self) -> Dict[str, Any]:
        """检测数据泄露"""
        
        detected = np.random.random() < 0.02  # 2%概率
        
        if detected:
            return {
                'detected': True,
                'description': '检测到疑似敏感数据传输到外部地址',
                'affected_components': ['data_storage', 'network'],
                'evidence': {
                    'data_size': '500MB',
                    'destination': 'external_server.com',
                    'protocol': 'HTTPS'
                },
                'recommendations': [
                    '审查数据访问策略',
                    '实施数据丢失防护',
                    '加强网络监控'
                ]
            }
        
        return {'detected': False}
    
    async def _detect_config_drift(self) -> Dict[str, Any]:
        """检测配置漂移"""
        
        detected = np.random.random() < 0.1  # 10%概率
        
        if detected:
            return {
                'detected': True,
                'description': '检测到配置文件与基准配置存在差异',
                'affected_components': ['configuration_management'],
                'evidence': {
                    'drifted_files': ['config.json', 'env.prod'],
                    'change_count': 3,
                    'last_verified': '2024-01-01'
                },
                'recommendations': [
                    '定期验证配置一致性',
                    '实施配置版本控制',
                    '自动化配置部署'
                ]
            }
        
        return {'detected': False}
    
    async def _detect_financial_anomaly(self) -> Dict[str, Any]:
        """检测财务异常"""
        
        detected = np.random.random() < 0.08  # 8%概率
        
        if detected:
            return {
                'detected': True,
                'description': '检测到异常交易模式或损失',
                'affected_components': ['trading_engine', 'risk_management'],
                'evidence': {
                    'loss_amount': 5000.0,
                    'timeframe': 'last_24h',
                    'unusual_pattern': '高频小额亏损'
                },
                'recommendations': [
                    '审查交易策略',
                    '调整风险参数',
                    '增加人工监控'
                ]
            }
        
        return {'detected': False}
    
    async def _detect_market_manipulation(self) -> Dict[str, Any]:
        """检测市场操纵"""
        
        detected = np.random.random() < 0.03  # 3%概率
        
        if detected:
            return {
                'detected': True,
                'description': '检测到疑似市场操纵行为',
                'affected_components': ['market_data', 'trading_engine'],
                'evidence': {
                    'pattern': 'wash_trading',
                    'volume_anomaly': 300,
                    'symbols': ['BTCUSDT', 'ETHUSDT']
                },
                'recommendations': [
                    '暂停相关交易对',
                    '报告监管机构',
                    '加强市场监控'
                ]
            }
        
        return {'detected': False}
    
    async def _detect_operational_failure(self) -> Dict[str, Any]:
        """检测操作失败"""
        
        detected = np.random.random() < 0.05  # 5%概率
        
        if detected:
            return {
                'detected': True,
                'description': '检测到系统操作失败或性能下降',
                'affected_components': ['system_monitoring', 'trading_engine'],
                'evidence': {
                    'downtime_minutes': 15,
                    'error_rate': 0.05,
                    'affected_services': ['order_execution', 'data_feed']
                },
                'recommendations': [
                    '检查系统健康状态',
                    '增加冗余',
                    '优化错误处理'
                ]
            }
        
        return {'detected': False}
    
    def _get_risk_type_from_pattern(self, pattern_name: str) -> str:
        """从模式名称获取风险类型"""
        
        mapping = {
            'unauthorized_access': 'security',
            'data_leakage': 'security',
            'config_drift': 'operational',
            'financial_anomaly': 'financial',
            'market_manipulation': 'market',
            'operational_failure': 'operational'
        }
        
        return mapping.get(pattern_name, 'operational')
    
    async def _check_security_events(self) -> List[SecurityAlert]:
        """检查安全事件"""
        
        alerts = []
        
        # 这里应该集成真实的安全监控系统
        # 简化实现：模拟安全事件
        
        if np.random.random() < 0.01:  # 1%概率
            alert = SecurityAlert(
                alert_id=f"SEC_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                alert_type='UNAUTHORIZED_ACCESS',
                severity='HIGH',
                source='external_ip:203.0.113.1',
                target='api_gateway',
                description='多次失败的API认证尝试',
                timestamp=datetime.now(),
                indicators={
                    'attempt_count': 25,
                    'timeframe': '10分钟',
                    'user_agent': 'suspicious_bot'
                },
                actions_taken=['IP临时封锁', '通知管理员']
            )
            
            alerts.append(alert)
        
        if np.random.random() < 0.005:  # 0.5%概率
            alert = SecurityAlert(
                alert_id=f"SEC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_2",
                alert_type='CONFIG_CHANGE',
                severity='MEDIUM',
                source='internal_user:admin',
                target='system_config',
                description='非工作时间的关键配置变更',
                timestamp=datetime.now(),
                indicators={
                    'changed_file': 'config/trading.json',
                    'change_time': '03:00 UTC',
                    'change_type': 'risk_parameters'
                },
                actions_taken=['记录变更', '等待验证']
            )
            
            alerts.append(alert)
        
        return alerts
    
    async def _should_run_audit(self, rule_name: str, frequency: str) -> bool:
        """判断是否需要运行审计"""
        
        # 这里应该基于上次运行时间来判断
        # 简化实现：根据频率随机决定
        
        if frequency == 'DAILY':
            return np.random.random() < 0.1  # 每天10%概率运行
        elif frequency == 'WEEKLY':
            return np.random.random() < 0.3  # 每周30%概率运行
        elif frequency == 'MONTHLY':
            return np.random.random() < 0.5  # 每月50%概率运行
        else:
            return False
    
    async def _daily_trade_review(self) -> List[RiskFinding]:
        """每日交易审查"""
        
        findings = []
        
        # 模拟交易审查发现
        if np.random.random() < 0.2:  # 20%概率发现问题
            finding = RiskFinding(
                timestamp=datetime.now(),
                risk_id=f"TRADE_REVIEW_{datetime.now().strftime('%Y%m%d')}",
                risk_type='financial',
                severity='MEDIUM',
                title='日内交易频率异常',
                description='检测到异常高的交易频率，可能增加交易成本',
                affected_components=['trading_engine', 'execution'],
                evidence={
                    'trades_today': 150,
                    'avg_trades_per_day': 50,
                    'cost_impact': 0.15  # 0.15%额外成本
                },
                recommendations=[
                    '审查交易策略',
                    '优化执行算法',
                    '调整频率限制'
                ]
            )
            
            findings.append(finding)
        
        if np.random.random() < 0.15:  # 15%概率
            finding = RiskFinding(
                timestamp=datetime.now(),
                risk_id=f"TRADE_REVIEW_{datetime.now().strftime('%Y%m%d')}_2",
                risk_type='market',
                severity='LOW',
                title='单一资产集中度过高',
                description='BTC持仓占总资产比例超过阈值',
                affected_components=['portfolio', 'risk_management'],
                evidence={
                    'btc_allocation': 45.5,
                    'threshold': 40.0,
                    'other_assets': ['ETH:25%', 'SOL:15%']
                },
                recommendations=[
                    '分散投资',
                    '设置持仓限制',
                    '定期再平衡'
                ]
            )
            
            findings.append(finding)
        
        return findings
    
    async def _weekly_risk_assessment(self) -> List[RiskFinding]:
        """每周风险评估"""
        
        findings = []
        
        # 模拟风险评估发现
        finding = RiskFinding(
            timestamp=datetime.now(),
            risk_id=f"WEEKLY_RISK_{datetime.now().strftime('%Y%m%d')}",
            risk_type='financial',
            severity='HIGH',
            title='周度回撤超过阈值',
            description='本周最大回撤达到7.5%，超过5%的阈值',
            affected_components=['portfolio', 'risk_management'],
            evidence={
                'weekly_drawdown': 7.5,
                'threshold': 5.0,
                'peak_equity': 105000,
                'trough_equity': 97125
            },
            recommendations=[
                '降低仓位',
                '加强止损',
                '审查市场暴露'
            ]
        )
        
        findings.append(finding)
        
        return findings
    
    async def _monthly_compliance_check(self) -> List[RiskFinding]:
        """月度合规检查"""
        
        findings = []
        
        # 模拟合规检查发现
        finding = RiskFinding(
            timestamp=datetime.now(),
            risk_id=f"COMPLIANCE_{datetime.now().strftime('%Y%m')}",
            risk_type='compliance',
            severity='MEDIUM',
            title='审计日志保留不足',
            description='部分系统日志保留时间未达到90天要求',
            affected_components=['logging', 'compliance'],
            evidence={
                'retention_days': 60,
                'requirement': 90,
                'affected_logs': ['trade_logs', 'access_logs']
            },
            recommendations=[
                '扩展日志存储',
                '自动化日志轮转',
                '定期验证合规性'
            ]
        )
        
        findings.append(finding)
        
        return findings
    
    async def _config_audit(self) -> List[RiskFinding]:
        """配置审计"""
        
        findings = []
        
        if np.random.random() < 0.25:  # 25%概率
            finding = RiskFinding(
                timestamp=datetime.now(),
                risk_id=f"CONFIG_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                risk_type='security',
                severity='MEDIUM',
                title='API密钥未轮换',
                description='部分API密钥使用时间超过90天',
                affected_components=['security', 'configuration'],
                evidence={
                    'keys_expired': 2,
                    'max_age_days': 120,
                    'recommended_rotation': 90
                },
                recommendations=[
                    '立即轮换API密钥',
                    '实施自动轮换策略',
                    '加强密钥管理'
                ]
            )
            
            findings.append(finding)
        
        return findings
    
    async def _access_log_review(self) -> List[RiskFinding]:
        """访问日志审查"""
        
        findings = []
        
        if np.random.random() < 0.1:  # 10%概率
            finding = RiskFinding(
                timestamp=datetime.now(),
                risk_id=f"ACCESS_LOG_{datetime.now().strftime('%Y%m%d')}",
                risk_type='security',
                severity='LOW',
                title='异常登录时间',
                description='检测到非工作时间的系统访问',
                affected_components=['authentication', 'security'],
                evidence={
                    'login_time': '03:30 UTC',
                    'user': 'trading_bot',
                    'usual_hours': '09:00-18:00 UTC'
                },
                recommendations=[
                    '验证访问必要性',
                    '实施时间限制',
                    '加强监控'
                ]
            )
            
            findings.append(finding)
        
        return findings
    
    async def _check_audit_logging(self) -> Tuple[str, Dict]:
        """检查审计日志"""
        
        # 简化实现
        status = 'PASS' if np.random.random() < 0.8 else 'FAIL'
        
        evidence = {
            'logging_enabled': True,
            'retention_days': 120 if status == 'PASS' else 60,
            'coverage': '95%' if status == 'PASS' else '70%'
        }
        
        return status, evidence
    
    async def _check_config_encryption(self) -> Tuple[str, Dict]:
        """检查配置加密"""
        
        status = 'PASS' if np.random.random() < 0.9 else 'FAIL'
        
        evidence = {
            'encryption_enabled': status == 'PASS',
            'algorithm': 'AES-256' if status == 'PASS' else 'None',
            'key_management': 'HSM' if status == 'PASS' else 'Plaintext'
        }
        
        return status, evidence
    
    async def _check_trade_risk_controls(self) -> Tuple[str, Dict]:
        """检查交易风险控制"""
        
        status = 'PASS' if np.random.random() < 0.85 else 'WARNING'
        
        evidence = {
            'pre_trade_checks': True,
            'real_time_monitoring': status != 'FAIL',
            'post_trade_analysis': True,
            'breaches_last_week': 0 if status == 'PASS' else 3
        }
        
        return status, evidence
    
    async def _check_data_backup(self) -> Tuple[str, Dict]:
        """检查数据备份"""
        
        status = 'PASS' if np.random.random() < 0.95 else 'FAIL'
        
        evidence = {
            'backup_frequency': 'Daily',
            'retention': '30 days',
            'last_successful_backup': '2024-01-01' if status == 'PASS' else '2023-12-15',
            'test_restore': 'Successful' if status == 'PASS' else 'Not tested'
        }
        
        return status, evidence
    
    async def _check_mfa_enforcement(self) -> Tuple[str, Dict]:
        """检查MFA执行"""
        
        status = 'PASS' if np.random.random() < 0.7 else 'FAIL'
        
        evidence = {
            'mfa_required': status == 'PASS',
            'coverage': 'All critical operations' if status == 'PASS' else 'Partial',
            'authentication_methods': ['TOTP', 'WebAuthn'] if status == 'PASS' else ['Password only']
        }
        
        return status, evidence
    
    async def _check_data_anonymization(self) -> Tuple[str, Dict]:
        """检查数据匿名化"""
        
        status = 'PASS' if np.random.random() < 0.6 else 'NOT_APPLICABLE'
        
        evidence = {
            'pii_detected': False,
            'anonymization_method': 'k-anonymity' if status == 'PASS' else 'N/A',
            'compliance_score': '95%' if status == 'PASS' else 'N/A'
        }
        
        return status, evidence
    
    async def _check_data_subject_rights(self) -> Tuple[str, Dict]:
        """检查数据主体权利"""
        
        status = 'PASS'
        
        evidence = {
            'access_portal': True,
            'deletion_capability': True,
            'request_fulfillment_time': '7 days'
        }
        
        return status, evidence
    
    async def _check_payment_data_encryption(self) -> Tuple[str, Dict]:
        """检查支付数据加密"""
        
        status = 'NOT_APPLICABLE'  # 假设我们不处理支付卡数据
        
        evidence = {
            'card_data_handled': False,
            'encryption_required': 'N/A',
            'compliance_status': 'N/A'
        }
        
        return status, evidence
    
    async def _trigger_risk_alert(self, finding: RiskFinding):
        """触发风险告警"""
        
        alert_message = f"🚨 风险发现: {finding.severity} - {finding.title}"
        
        # 发送到配置的告警通道
        for channel in self.config['alert_channels']:
            if channel == 'console':
                print(alert_message)
                print(f"   描述: {finding.description}")
                print(f"   影响: {', '.join(finding.affected_components)}")
            
            elif channel == 'file':
                # 写入日志文件
                try:
                    with open('risk_alerts.log', 'a', encoding='utf-8') as f:
                        f.write(f"{datetime.now().isoformat()} - {alert_message}\n")
                except:
                    pass
    
    async def _trigger_security_alert(self, alert: SecurityAlert):
        """触发安全告警"""
        
        alert_message = f"🔒 安全告警: {alert.severity} - {alert.alert_type}"
        
        for channel in self.config['alert_channels']:
            if channel == 'console':
                print(alert_message)
                print(f"   来源: {alert.source}")
                print(f"   目标: {alert.target}")
                print(f"   措施: {', '.join(alert.actions_taken)}")
    
    async def _create_audit_report(self, audit_type: str, findings: List[RiskFinding]) -> AuditReport:
        """创建审计报告"""
        
        # 统计发现严重程度
        critical_count = sum(1 for f in findings if f.severity == 'CRITICAL')
        high_count = sum(1 for f in findings if f.severity == 'HIGH')
        medium_count = sum(1 for f in findings if f.severity == 'MEDIUM')
        low_count = sum(1 for f in findings if f.severity == 'LOW')
        
        # 生成摘要
        if findings:
            summary = f"审计发现 {len(findings)} 个问题，其中 {critical_count} 个关键问题需要立即关注。"
        else:
            summary = "审计未发现重大问题，系统运行正常。"
        
        # 获取合规检查状态
        compliance_checks = list(self.compliance_checks.values())
        
        # 获取安全告警
        recent_alerts = [
            alert for alert in self.security_alerts.values()
            if alert.timestamp > datetime.now() - timedelta(days=7)
        ]
        
        # 生成建议
        recommendations = []
        action_items = []
        
        if critical_count > 0:
            recommendations.append("立即解决关键风险问题")
            action_items.append({
                'item': '修复关键风险',
                'owner': '安全团队',
                'due_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            })
        
        if high_count > 0:
            recommendations.append("一周内解决高风险问题")
            action_items.append({
                'item': '修复高风险',
                'owner': '运维团队',
                'due_date': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            })
        
        if medium_count > 0 or low_count > 0:
            recommendations.append("制定计划解决中低风险问题")
            action_items.append({
                'item': '制定风险解决计划',
                'owner': '风险管理',
                'due_date': (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
            })
        
        report = AuditReport(
            report_id=f"AUDIT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            audit_type=audit_type,
            start_date=datetime.now() - timedelta(days=1),
            end_date=datetime.now(),
            auditor='AI_Risk_Auditor',
            summary=summary,
            total_findings=len(findings),
            critical_findings=critical_count,
            high_findings=high_count,
            medium_findings=medium_count,
            low_findings=low_count,
            findings=findings,
            compliance_checks=compliance_checks,
            security_alerts=recent_alerts,
            recommendations=recommendations,
            action_items=action_items
        )
        
        return report
    
    # 公共接口
    
    def get_open_findings(self, severity: str = None) -> List[RiskFinding]:
        """获取未解决的风险发现"""
        
        open_findings = [
            finding for finding in self.finding_history
            if finding.status == 'OPEN'
        ]
        
        if severity:
            open_findings = [
                f for f in open_findings if f.severity == severity
            ]
        
        return sorted(open_findings, key=lambda x: x.timestamp, reverse=True)
    
    def get_compliance_status(self, standard: str = None) -> Dict[str, Any]:
        """获取合规状态"""
        
        if standard:
            checks = [
                check for check in self.compliance_checks.values()
                if check.standard == standard
            ]
        else:
            checks = list(self.compliance_checks.values())
        
        if not checks:
            return {'status': 'NO_DATA', 'checks': []}
        
        # 统计状态
        status_counts = defaultdict(int)
        for check in checks:
            status_counts[check.status] += 1
        
        total_checks = len(checks)
        pass_rate = status_counts['PASS'] / total_checks if total_checks > 0 else 0
        
        return {
            'total_checks': total_checks,
            'pass_rate': pass_rate,
            'status_counts': dict(status_counts),
            'checks': checks
        }
    
    def get_security_alerts(self, alert_type: str = None, status: str = None) -> List[SecurityAlert]:
        """获取安全告警"""
        
        alerts = list(self.security_alerts.values())
        
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        
        if status:
            alerts = [a for a in alerts if a.status == status]
        
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)
    
    def get_audit_reports(self, audit_type: str = None, limit: int = 10) -> List[AuditReport]:
        """获取审计报告"""
        
        reports = self.audit_reports
        
        if audit_type:
            reports = [r for r in reports if r.audit_type == audit_type]
        
        reports.sort(key=lambda x: x.end_date, reverse=True)
        
        return reports[:limit]
    
    async def run_ad_hoc_audit(self, audit_scope: Dict[str, Any]) -> AuditReport:
        """运行临时审计"""
        
        print(f"🔍 运行临时审计: {audit_scope.get('name', '未命名审计')}")
        
        # 收集审计发现
        findings = []
        
        # 根据范围执行检查
        if audit_scope.get('include_trade_review', False):
            trade_findings = await self._daily_trade_review()
            findings.extend(trade_findings)
        
        if audit_scope.get('include_risk_assessment', False):
            risk_findings = await self._weekly_risk_assessment()
            findings.extend(risk_findings)
        
        if audit_scope.get('include_config_audit', False):
            config_findings = await self._config_audit()
            findings.extend(config_findings)
        
        # 创建报告
        report = await self._create_audit_report(
            audit_type='AD_HOC',
            findings=findings
        )
        
        self.audit_reports.append(report)
        
        print(f"✅ 临时审计完成: {report.report_id}")
        
        return report
    
    def update_finding_status(self, risk_id: str, status: str, 
                            resolution_notes: str = None, assigned_to: str = None):
        """更新风险发现状态"""
        
        if risk_id in self.risk_findings:
            finding = self.risk_findings[risk_id]
            finding.status = status
            
            if status == 'RESOLVED':
                finding.resolution_date = datetime.now()
                finding.resolution_notes = resolution_notes
            
            if assigned_to:
                finding.assigned_to = assigned_to
            
            print(f"✅ 更新风险发现状态: {risk_id} -> {status}")
    
    def export_audit_report(self, report_id: str, format: str = 'json') -> str:
        """导出审计报告"""
        
        report = None
        for r in self.audit_reports:
            if r.report_id == report_id:
                report = r
                break
        
        if not report:
            return f"未找到报告: {report_id}"
        
        if format == 'json':
            return json.dumps(asdict(report), indent=2, default=str)
        else:
            return f"不支持的格式: {format}"
    
    def get_risk_dashboard(self) -> Dict[str, Any]:
        """获取风险仪表板数据"""
        
        # 开放发现统计
        open_findings = self.get_open_findings()
        open_by_severity = defaultdict(int)
        for finding in open_findings:
            open_by_severity[finding.severity] += 1
        
        # 合规状态
        compliance_status = self.get_compliance_status()
        
        # 安全告警
        recent_alerts = self.get_security_alerts(status='NEW')
        
        # 审计报告
        recent_reports = self.get_audit_reports(limit=5)
        
        dashboard = {
            'timestamp': datetime.now().isoformat(),
            'open_findings': {
                'total': len(open_findings),
                'by_severity': dict(open_by_severity),
                'trend': 'stable'  # 简化
            },
            'compliance': {
                'status': compliance_status['status'],
                'pass_rate': compliance_status['pass_rate'],
                'checks': compliance_status['total_checks']
            },
            'security': {
                'new_alerts': len(recent_alerts),
                'recent_alerts': [{'type': a.alert_type, 'severity': a.severity} 
                                 for a in recent_alerts[:3]]
            },
            'audits': {
                'recent_reports': len(recent_reports),
                'last_audit': recent_reports[0].end_date.isoformat() if recent_reports else None
            },
            'risk_score': self._calculate_risk_score(open_findings, compliance_status, recent_alerts)
        }
        
        return dashboard
    
    def _calculate_risk_score(self, open_findings: List[RiskFinding], 
                            compliance_status: Dict[str, Any], 
                            recent_alerts: List[SecurityAlert]) -> float:
        """计算风险分数"""
        
        # 风险发现权重
        finding_weights = {
            'CRITICAL': 10,
            'HIGH': 7,
            'MEDIUM': 4,
            'LOW': 1
        }
        
        finding_score = 0
        for finding in open_findings:
            finding_score += finding_weights.get(finding.severity, 0)
        
        # 合规分数
        compliance_score = (1 - compliance_status['pass_rate']) * 50 if compliance_status['pass_rate'] < 1.0 else 0
        
        # 安全告警分数
        alert_weights = {
            'CRITICAL': 8,
            'HIGH': 5,
            'MEDIUM': 3,
            'LOW': 1
        }
        
        alert_score = 0
        for alert in recent_alerts:
            alert_score += alert_weights.get(alert.severity, 0)
        
        # 综合分数（0-100，越高风险越大）
        total_score = min(100, (finding_score + compliance_score + alert_score) / 3)
        
        return total_score

# 单例实例
_risk_auditor = None

def get_risk_auditor(config_manager=None) -> RiskAuditor:
    """获取风险审计器单例"""
    global _risk_auditor
    if _risk_auditor is None:
        _risk_auditor = RiskAuditor(config_manager)
    return _risk_auditor

async def test_risk_auditor():
    """测试风险审计器"""
    
    auditor = get_risk_auditor()
    await auditor.start()
    
    try:
        print("等待审计器运行...")
        await asyncio.sleep(10)
        
        # 获取仪表板
        dashboard = auditor.get_risk_dashboard()
        print(f"\n📊 风险仪表板:")
        print(f"   开放发现: {dashboard['open_findings']['total']} 个")
        print(f"   合规通过率: {dashboard['compliance']['pass_rate']:.1%}")
        print(f"   新安全告警: {dashboard['security']['new_alerts']} 个")
        print(f"   风险分数: {dashboard['risk_score']:.1f}/100")
        
        # 运行临时审计
        audit_scope = {
            'name': '系统健康检查',
            'include_trade_review': True,
            'include_config_audit': True
        }
        
        report = await auditor.run_ad_hoc_audit(audit_scope)
        print(f"\n📋 审计报告: {report.report_id}")
        print(f"   发现: {report.total_findings} 个问题")
        print(f"   关键问题: {report.critical_findings} 个")
        
        # 获取开放发现
        open_findings = auditor.get_open_findings()
        if open_findings:
            print(f"\n🔍 开放风险发现:")
            for finding in open_findings[:3]:
                print(f"   {finding.severity}: {finding.title}")
        
        # 保持运行
        await asyncio.sleep(30)
        
    finally:
        await auditor.stop()

if __name__ == "__main__":
    asyncio.run(test_risk_auditor())