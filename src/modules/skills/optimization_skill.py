"""
优化建议技能 - 提供系统优化建议
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class OptimizationSkill(SkillBase):
    """优化建议技能"""
    
    def __init__(self):
        super().__init__(
            name="optimization",
            description="分析系统表现并提供优化建议",
            priority=SkillPriority.MEDIUM
        )
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行优化分析"""
        analysis = await self.diagnose(context)
        
        recommendations = []
        
        for rec in analysis.get("recommendations", []):
            recommendations.append(f"{rec['category']}: {rec['suggestion']}")
        
        return SkillResult(
            skill_name=self.name,
            status=SkillStatus.SUCCESS,
            priority=self.priority,
            message=f"生成了 {len(recommendations)} 条优化建议",
            data=analysis,
            recommendations=recommendations
        )
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """诊断并生成建议"""
        trading_engine = context.get("trading_engine")
        performance_data = context.get("performance_data", {})
        
        recommendations = []
        
        if trading_engine:
            recommendations.extend(self._analyze_trading_strategy(trading_engine))
            recommendations.extend(self._analyze_risk_management(trading_engine))
        
        recommendations.extend(self._analyze_system_performance(performance_data))
        recommendations.extend(self._analyze_configuration(context))
        
        return {
            "timestamp": datetime.now().isoformat(),
            "recommendations": recommendations,
            "priority_actions": self._prioritize_recommendations(recommendations)
        }
    
    def _analyze_trading_strategy(self, engine) -> List[Dict[str, Any]]:
        """分析交易策略"""
        recommendations = []
        
        trade_history = getattr(engine, 'trade_history', [])
        if len(trade_history) < 10:
            recommendations.append({
                "category": "数据积累",
                "suggestion": "继续积累交易数据以进行更准确的分析",
                "priority": "low",
                "impact": "长期改进"
            })
        
        positions = getattr(engine, 'positions', {})
        if len(positions) > 3:
            recommendations.append({
                "category": "仓位管理",
                "suggestion": "考虑减少同时持仓数量，集中精力管理好现有持仓",
                "priority": "medium",
                "impact": "降低风险"
            })
        
        return recommendations
    
    def _analyze_risk_management(self, engine) -> List[Dict[str, Any]]:
        """分析风险管理"""
        recommendations = []
        
        positions = getattr(engine, 'positions', {})
        
        for symbol, position in positions.items():
            if isinstance(position, dict):
                stop_loss = position.get('stop_loss')
                if not stop_loss:
                    recommendations.append({
                        "category": "风险控制",
                        "suggestion": f"为 {symbol} 设置止损，保护资金安全",
                        "priority": "high",
                        "impact": "防止大额亏损"
                    })
        
        return recommendations
    
    def _analyze_system_performance(self, performance_data) -> List[Dict[str, Any]]:
        """分析系统性能"""
        recommendations = []
        
        if performance_data.get("cpu_usage", 0) > 70:
            recommendations.append({
                "category": "性能优化",
                "suggestion": "优化计算密集型任务，考虑使用异步处理",
                "priority": "medium",
                "impact": "提升响应速度"
            })
        
        if performance_data.get("memory_usage", 0) > 80:
            recommendations.append({
                "category": "内存管理",
                "suggestion": "检查内存泄漏，优化数据缓存策略",
                "priority": "medium",
                "impact": "提升稳定性"
            })
        
        return recommendations
    
    def _analyze_configuration(self, context) -> List[Dict[str, Any]]:
        """分析配置"""
        recommendations = []
        
        recommendations.append({
            "category": "系统维护",
            "suggestion": "定期清理日志文件，保持系统轻量",
            "priority": "low",
            "impact": "节省磁盘空间"
        })
        
        recommendations.append({
            "category": "数据备份",
            "suggestion": "定期备份交易数据和配置文件",
            "priority": "medium",
            "impact": "数据安全"
        })
        
        return recommendations
    
    def _prioritize_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """优先级排序"""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        
        return sorted(
            recommendations,
            key=lambda x: priority_order.get(x.get("priority", "low"), 2)
        )
