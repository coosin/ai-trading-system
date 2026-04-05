"""
风险评估技能 - 评估当前交易风险
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class RiskAssessmentSkill(SkillBase):
    """风险评估技能"""
    
    def __init__(self):
        super().__init__(
            name="risk_assessment",
            description="评估当前交易风险，包括持仓风险、账户风险、市场风险",
            priority=SkillPriority.CRITICAL
        )
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行风险评估"""
        assessment = await self.diagnose(context)
        
        recommendations = []
        issues = []
        
        if assessment["account"]["risk_level"] == "critical":
            issues.append("账户风险等级: 严重")
            recommendations.append("立即减仓或平仓")
        
        if assessment["positions"]["high_risk_count"] > 0:
            issues.append(f"高风险持仓: {assessment['positions']['high_risk_count']} 个")
            recommendations.append("检查持仓止损设置")
        
        if assessment["account"]["margin_usage"] > 0.8:
            issues.append(f"保证金使用率过高: {assessment['account']['margin_usage']:.1%}")
            recommendations.append("降低杠杆或减少持仓")
        
        if assessment["market"]["volatility"] == "extreme":
            issues.append("市场波动极端")
            recommendations.append("谨慎交易或暂停开新仓")
        
        status = SkillStatus.SUCCESS
        if assessment["account"]["risk_level"] == "critical":
            status = SkillStatus.FAILED
        elif issues:
            status = SkillStatus.SUCCESS
        
        message = f"风险等级: {assessment['account']['risk_level']}"
        
        return SkillResult(
            skill_name=self.name,
            status=status,
            priority=self.priority,
            message=message,
            data=assessment,
            recommendations=recommendations,
            errors=issues
        )
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """诊断风险"""
        trading_engine = context.get("trading_engine")
        risk_monitor = context.get("risk_monitor")
        
        if not trading_engine:
            return self._get_default_assessment()
        
        account_risk = self._assess_account_risk(trading_engine, risk_monitor)
        positions_risk = self._assess_positions_risk(trading_engine)
        market_risk = self._assess_market_risk(trading_engine)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "account": account_risk,
            "positions": positions_risk,
            "market": market_risk
        }
    
    def _assess_account_risk(self, engine, risk_monitor) -> Dict[str, Any]:
        """评估账户风险"""
        if risk_monitor and hasattr(risk_monitor, 'get_current_risk'):
            try:
                current_risk = risk_monitor.get_current_risk()
                return {
                    "risk_level": current_risk.get("risk_level", "unknown"),
                    "margin_usage": current_risk.get("margin_usage", 0),
                    "total_equity": current_risk.get("total_equity", 0),
                    "available_balance": current_risk.get("available_balance", 0)
                }
            except:
                pass
        
        positions = getattr(engine, 'positions', {})
        balance = getattr(engine, 'balance', 0)
        
        total_position_value = sum(
            abs(p.get('quantity', 0) * p.get('current_price', 0))
            for p in positions.values()
            if isinstance(p, dict)
        )
        
        margin_usage = total_position_value / balance if balance > 0 else 0
        
        risk_level = "low"
        if margin_usage > 0.9:
            risk_level = "critical"
        elif margin_usage > 0.7:
            risk_level = "high"
        elif margin_usage > 0.5:
            risk_level = "medium"
        
        return {
            "risk_level": risk_level,
            "margin_usage": margin_usage,
            "total_equity": balance,
            "available_balance": balance - total_position_value
        }
    
    def _assess_positions_risk(self, engine) -> Dict[str, Any]:
        """评估持仓风险"""
        positions = getattr(engine, 'positions', {})
        
        total_positions = len(positions)
        high_risk_count = 0
        position_risks = []
        
        for symbol, position in positions.items():
            if isinstance(position, dict):
                pnl_percent = position.get('unrealized_pnl_percent', 0)
                
                risk_level = "low"
                if pnl_percent < -10:
                    risk_level = "critical"
                    high_risk_count += 1
                elif pnl_percent < -5:
                    risk_level = "high"
                    high_risk_count += 1
                elif pnl_percent < -2:
                    risk_level = "medium"
                
                position_risks.append({
                    "symbol": symbol,
                    "risk_level": risk_level,
                    "pnl_percent": pnl_percent
                })
        
        return {
            "total_positions": total_positions,
            "high_risk_count": high_risk_count,
            "positions": position_risks
        }
    
    def _assess_market_risk(self, engine) -> Dict[str, Any]:
        """评估市场风险"""
        return {
            "volatility": "normal",
            "trend": "neutral",
            "sentiment": "neutral"
        }
    
    def _get_default_assessment(self) -> Dict[str, Any]:
        """获取默认评估"""
        return {
            "timestamp": datetime.now().isoformat(),
            "account": {
                "risk_level": "unknown",
                "margin_usage": 0,
                "total_equity": 0,
                "available_balance": 0
            },
            "positions": {
                "total_positions": 0,
                "high_risk_count": 0,
                "positions": []
            },
            "market": {
                "volatility": "unknown",
                "trend": "unknown",
                "sentiment": "unknown"
            }
        }
