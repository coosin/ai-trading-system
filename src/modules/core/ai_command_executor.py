"""
AI 指令执行器 - 完整版
能够真正调用交易系统的各个功能模块
集成统一记忆系统和用户意图识别
"""

import asyncio
import logging
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """用户意图"""
    action: str
    params: Dict[str, Any]
    confidence: float


class AICommandExecutor:
    """
    AI 指令执行器 - 完整版
    
    功能：
    1. AI自由理解用户意图，无预设限制
    2. 调用交易系统实际功能
    3. 返回真实执行结果
    4. 自动识别和记录用户指令/偏好
    5. 集成统一记忆系统
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        self.llm_integration = None
        self.memory_manager = None
        self.unified_memory = None
        self.user_intent_recognizer = None
        
        logger.info("AI指令执行器（完整版）初始化完成")
    
    async def initialize(self) -> None:
        """初始化指令执行器"""
        logger.info("初始化AI指令执行器（完整版）...")
        
        if self.main_controller:
            if hasattr(self.main_controller, 'llm_integration'):
                self.llm_integration = self.main_controller.llm_integration
            
            if hasattr(self.main_controller, 'ai_memory_manager'):
                self.memory_manager = self.main_controller.ai_memory_manager
        
        try:
            from .unified_intelligent_memory import get_unified_memory
            from .user_intent_recognizer import UserIntentRecognizer
            
            self.unified_memory = get_unified_memory()
            self.user_intent_recognizer = UserIntentRecognizer
            logger.info("✅ 统一记忆系统和用户意图识别器已加载")
        except Exception as e:
            logger.warning(f"加载统一记忆系统失败: {e}")
        
        logger.info("✅ AI指令执行器（完整版）初始化完成")
    
    async def process_input(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入 - 解析意图并执行实际功能
        自动识别和记录用户指令/偏好
        """
        logger.info(f"处理用户输入: {user_input}")
        
        try:
            if self.unified_memory:
                memory_result = await self.unified_memory.process_user_input(user_input)
                if memory_result.get("recorded"):
                    logger.info(f"📝 自动记录用户意图: {memory_result.get('message')}")
            
            intent = await self._parse_intent(user_input)
            
            if intent.action != "unknown":
                result = await self._execute_intent(intent, user_input)
            else:
                result = await self._general_chat(user_input)
            
            if self.unified_memory:
                await self.unified_memory.add_memory(
                    memory_type=self._get_memory_type_from_intent(intent.action),
                    content=f"用户: {user_input}",
                    summary=f"用户指令: {user_input[:100]}",
                    metadata={"intent": intent.action, "params": intent.params},
                    source_module="ai_command_executor"
                )
                await self.unified_memory.add_memory(
                    memory_type=self._get_memory_type_from_intent(intent.action),
                    content=f"AI响应: {result.get('response', '')[:300]}",
                    summary=f"AI响应: {result.get('response', '')[:100]}",
                    metadata={"intent": intent.action},
                    source_module="ai_command_executor"
                )
            elif self.memory_manager:
                await self.memory_manager.add_short_term_memory(
                    f"用户: {user_input}",
                    importance=0.7
                )
                await self.memory_manager.add_short_term_memory(
                    f"AI: {result.get('response', '')[:300]}...",
                    importance=0.7
                )
            
            return result
            
        except Exception as e:
            logger.error(f"处理用户输入失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "response": f"执行过程中出错：{str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _get_memory_type_from_intent(self, action: str):
        """根据意图类型获取记忆类型"""
        from .unified_intelligent_memory import UnifiedMemoryType
        
        mapping = {
            "trade": UnifiedMemoryType.TRADING_DECISION,
            "signals": UnifiedMemoryType.AI_PREDICTION,
            "market_analysis": UnifiedMemoryType.MARKET_INSIGHT,
            "risk": UnifiedMemoryType.RISK_SETTING,
            "strategy_create": UnifiedMemoryType.STRATEGY_GENERATED,
            "strategy_optimize": UnifiedMemoryType.RL_OPTIMIZATION,
        }
        return mapping.get(action, UnifiedMemoryType.CONVERSATION)
    
    async def _parse_intent(self, user_input: str) -> Intent:
        """解析用户意图 - 使用LLM自由理解，无预设限制"""
        
        if self.llm_integration:
            try:
                prompt = f"""你是一个量化交易系统的AI助手。用户发送了以下消息，请理解用户的真实意图。

用户消息: {user_input}

请分析用户想要做什么，并以JSON格式返回：
{{
    "action": "动作类型（如: trade, market_analysis, strategy_create, strategy_optimize, balance, positions, signals, risk, backtest, system_status, chat等）",
    "params": {{相关参数}},
    "confidence": 0.0-1.0的置信度,
    "reasoning": "简短解释你如何理解用户意图"
}}

注意：
1. 自由理解用户意图，不要局限于预设的动作类型
2. 如果用户想开发新策略，action为strategy_create
3. 如果用户想优化策略，action为strategy_optimize  
4. 如果用户想交易，action为trade
5. 如果是普通聊天，action为chat
6. 提取所有相关参数（交易对、数量、方向等）

只返回JSON，不要其他内容。"""

                response = await self.llm_integration.generate_response(prompt)
                
                if response:
                    import json
                    try:
                        result = json.loads(response)
                        return Intent(
                            action=result.get("action", "chat"),
                            params=result.get("params", {}),
                            confidence=result.get("confidence", 0.8)
                        )
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.warning(f"LLM解析意图失败: {e}")
        
        params = await self._extract_params(user_input, "")
        return Intent(action="chat", params=params, confidence=0.5)
    
    async def _extract_params(self, user_input: str, action: str) -> Dict[str, Any]:
        """提取参数"""
        params = {}
        
        import re
        
        symbols = re.findall(r'\b(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|DOT|MATIC)[-/]?(USDT|USDT|USD)?\b', user_input, re.IGNORECASE)
        if symbols:
            params['symbol'] = symbols[0][0].upper() + '/USDT'
        
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', user_input)
        if numbers:
            if '天' in user_input or '日' in user_input:
                params['days'] = int(numbers[0])
            elif '%' in user_input:
                params['percentage'] = float(numbers[0])
            else:
                params['value'] = float(numbers[0])
        
        return params
    
    async def _execute_intent(self, intent: Intent, user_input: str) -> Dict[str, Any]:
        """执行意图 - AI自主决策，无限制"""
        action = intent.action
        params = intent.params
        
        try:
            if action == "backtest":
                return await self._execute_backtest(params)
            elif action == "strategy_list":
                return await self._get_strategy_list()
            elif action == "strategy_create":
                return await self._create_strategy(params, user_input)
            elif action == "strategy_optimize":
                return await self._optimize_strategy(params, user_input)
            elif action == "strategy_combine":
                return await self._combine_strategies(params, user_input)
            elif action == "strategy_switch":
                return await self._switch_strategy(params, user_input)
            elif action == "market_analysis":
                return await self._analyze_market(params)
            elif action == "market_data":
                return await self._get_market_data(params)
            elif action == "balance":
                return await self._get_balance()
            elif action == "positions":
                return await self._get_positions()
            elif action == "signals":
                return await self._get_signals()
            elif action == "risk":
                return await self._analyze_risk()
            elif action == "trade":
                return await self._execute_trade(params, user_input)
            elif action == "third_party_data":
                return await self._get_third_party_data(params, user_input)
            elif action == "system_status":
                return await self._get_system_status()
            elif action == "chat":
                return await self._general_chat(user_input)
            else:
                return await self._ai_autonomous_action(action, params, user_input)
                
        except Exception as e:
            logger.error(f"执行意图失败: {action} - {e}")
            return {
                "success": False,
                "response": f"执行 {action} 失败：{str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    async def _execute_backtest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行策略回测"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                strategy_configs = sm.strategy_configs
                if strategy_configs:
                    strategy_id = list(strategy_configs.keys())[0]
                    days = params.get('days', 30)
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=days)
                    
                    result = await sm.backtest_strategy(
                        strategy_id=strategy_id,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    return {
                        "success": True,
                        "response": f"""📊 策略回测结果

策略ID: {strategy_id}
回测周期: {days}天

总收益率: {result.get('total_return', 0)*100:.2f}%
最大回撤: {result.get('max_drawdown', 0)*100:.2f}%
夏普比率: {result.get('sharpe_ratio', 0):.2f}
胜率: {result.get('win_rate', 0)*100:.1f}%
交易次数: {result.get('total_trades', 0)}

详细数据已保存到记忆系统。""",
                        "data": result,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {"success": False, "response": "没有可用的策略进行回测"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            return {"success": False, "response": f"回测失败: {str(e)}"}
    
    async def _get_strategy_list(self) -> Dict[str, Any]:
        """获取策略列表"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                strategies = []
                for strategy_id, config in sm.strategy_configs.items():
                    strategies.append({
                        'id': strategy_id,
                        'name': config.name,
                        'status': 'active' if config.enabled else 'inactive',
                        'returns': 0,
                        'max_drawdown': 0,
                        'sharpe_ratio': 0
                    })
                
                if strategies:
                    response = "📋 策略列表\n\n"
                    for s in strategies:
                        status_emoji = "🟢" if s.get('status') == 'active' else "🔴"
                        response += f"""{status_emoji} {s.get('name', 'Unknown')}
   ID: {s.get('id', 'N/A')}
   状态: {s.get('status', 'N/A')}
   收益率: {s.get('returns', 0)}%
   最大回撤: {s.get('max_drawdown', 0)}%
   夏普比率: {s.get('sharpe_ratio', 0)}

"""
                    return {"success": True, "response": response, "data": strategies}
                else:
                    return {"success": True, "response": "暂无策略，可以使用'创建策略'命令新建策略"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取策略列表失败: {str(e)}"}
    
    async def _create_strategy(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """创建策略"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                if self.llm_integration:
                    prompt = f"""根据用户需求生成交易策略配置：
用户需求：{user_input}

请以JSON格式返回策略配置，包含：
- name: 策略名称
- type: 策略类型 (trend_following, mean_reversion, arbitrage, ml_based)
- parameters: 策略参数
- risk_config: 风险配置

只返回JSON，不要其他内容。"""
                    
                    response = await self.llm_integration.generate(prompt)
                    if response.success:
                        import json
                        strategy_config = json.loads(response.content)
                        
                        strategy_config_data = {
                            "strategy_id": f"custom_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "name": strategy_config.get('name', 'Custom Strategy'),
                            "description": strategy_config.get('description', 'User created strategy'),
                            "strategy_type": strategy_config.get('type', 'trend_following'),
                            "parameters": strategy_config.get('parameters', {}),
                            "symbols": params.get('symbol', 'BTC/USDT').split(',') if params.get('symbol') else ['BTC/USDT'],
                            "timeframe": "1h",
                            "initial_capital": 10000.0
                        }
                        
                        config = await sm.load_strategy_config(strategy_config_data)
                        
                        return {
                            "success": True,
                            "response": f"""✅ 策略创建成功

策略名称: {strategy_config.get('name', 'Unknown')}
策略类型: {strategy_config.get('type', 'Unknown')}
策略ID: {strategy_config_data['strategy_id']}

可以使用'回测'命令测试策略表现。""",
                            "data": {"strategy_id": strategy_config_data['strategy_id'], "config": strategy_config}
                        }
                
                return {"success": False, "response": "策略创建失败：无法生成策略配置"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"创建策略失败: {str(e)}"}
    
    async def _optimize_strategy(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """优化策略"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'parameter_optimizer'):
                optimizer = self.main_controller.parameter_optimizer
                
                if self.main_controller.strategy_manager:
                    strategies = await self.main_controller.strategy_manager.list_strategies()
                    if strategies:
                        strategy_id = strategies[0].get('id', '1')
                        
                        result = await optimizer.optimize(strategy_id=strategy_id)
                        
                        return {
                            "success": True,
                            "response": f"""✅ 策略优化完成

策略ID: {strategy_id}
优化结果: {result.get('improvement', 'N/A')}
新参数: {result.get('best_params', {})}

建议使用回测验证优化效果。""",
                            "data": result
                        }
                
                return {"success": False, "response": "没有可优化的策略"}
            
            return {"success": False, "response": "参数优化器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"策略优化失败: {str(e)}"}
    
    async def _analyze_market(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """分析市场"""
        try:
            symbol = params.get('symbol', 'BTC/USDT')
            
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                
                if engine.exchange:
                    ticker = await engine.exchange.get_ticker(symbol.replace('/', '-'))
                    klines = await engine.exchange.get_klines(symbol.replace('/', '-'), '1d', 30)
                    
                    if self.llm_integration and ticker:
                        prompt = f"""分析以下市场数据：

交易对: {symbol}
当前价格: {ticker.get('last', 0)}
24h最高: {ticker.get('high', 0)}
24h最低: {ticker.get('low', 0)}
24h成交量: {ticker.get('volume', 0)}

请提供：
1. 市场趋势分析（上涨/下跌/震荡）
2. 关键支撑位和阻力位
3. 技术指标解读
4. 市场情绪判断
5. 交易建议

以简洁的格式返回分析结果。"""
                        
                        response = await self.llm_integration.generate(prompt)
                        if response.success:
                            return {
                                "success": True,
                                "response": f"📊 {symbol} 市场分析\n\n{response.content}",
                                "data": {"symbol": symbol, "ticker": ticker}
                            }
            
            return {"success": False, "response": "市场分析失败：数据获取失败"}
            
        except Exception as e:
            return {"success": False, "response": f"市场分析失败: {str(e)}"}
    
    async def _get_market_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取市场数据"""
        try:
            symbol = params.get('symbol', 'BTC/USDT')
            
            if self.main_controller and hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
                
                ticker = await okx.get_ticker(symbol.replace('/', '-'))
                
                if ticker:
                    return {
                        "success": True,
                        "response": f"""📈 {symbol} 实时行情

当前价格: ${ticker.get('last', 0):,.2f}
买一价: ${ticker.get('bid', 0):,.2f}
卖一价: ${ticker.get('ask', 0):,.2f}
24h最高: ${ticker.get('high', 0):,.2f}
24h最低: ${ticker.get('low', 0):,.2f}
24h成交量: {ticker.get('volume', 0):,.2f}
24h涨跌幅: {ticker.get('change', 0)*100:.2f}%

数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}""",
                        "data": ticker
                    }
            
            return {"success": False, "response": "获取市场数据失败"}
            
        except Exception as e:
            return {"success": False, "response": f"获取市场数据失败: {str(e)}"}
    
    async def _get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
                balance = await okx.get_balance()
                
                if balance:
                    response = "💰 账户余额\n\n"
                    total = 0
                    for currency, amount in balance.items():
                        if isinstance(amount, dict):
                            free = amount.get('free', 0)
                            total += amount.get('total', free)
                            response += f"{currency}: {free:,.4f}\n"
                        else:
                            total += amount
                            response += f"{currency}: {amount:,.4f}\n"
                    response += f"\n总权益: ${total:,.2f}\n"
                    
                    return {"success": True, "response": response, "data": {"currencies": balance, "total": total}}
            
            return {"success": False, "response": "获取余额失败：交易所未连接"}
            
        except Exception as e:
            return {"success": False, "response": f"获取余额失败: {str(e)}"}
    
    async def _get_positions(self) -> Dict[str, Any]:
        """获取持仓"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
                positions = await okx.get_positions()
                
                if positions:
                    response = "📊 当前持仓\n\n"
                    total_pnl = 0
                    for pos in positions:
                        side_emoji = "🟢" if pos.get('side') == 'long' else "🔴"
                        pnl = pos.get('unrealized_pnl', 0)
                        total_pnl += pnl
                        
                        response += f"""{side_emoji} {pos.get('symbol', 'Unknown')}
   方向: {pos.get('side', 'N/A').upper()}
   数量: {pos.get('quantity', 0):.4f}
   入场价: ${pos.get('entry_price', 0):,.2f}
   当前价: ${pos.get('current_price', 0):,.2f}
   盈亏: ${pnl:+,.2f}

"""
                    response += f"总盈亏: ${total_pnl:+,.2f}\n"
                    
                    return {"success": True, "response": response, "data": positions}
                else:
                    return {"success": True, "response": "📭 当前没有任何持仓"}
            
            return {"success": False, "response": "获取持仓失败：交易所未连接"}
            
        except Exception as e:
            return {"success": False, "response": f"获取持仓失败: {str(e)}"}
    
    async def _get_signals(self) -> Dict[str, Any]:
        """获取交易信号"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                signals = getattr(engine, 'recent_signals', [])
                
                if signals:
                    response = "📈 最新交易信号\n\n"
                    for i, signal in enumerate(signals[:5], 1):
                        action_emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(
                            signal.get('action', 'hold').lower(), "⚪"
                        )
                        response += f"""{i}. {signal.get('symbol', 'Unknown')} - {action_emoji} {signal.get('action', 'N/A').upper()}
   入场: ${signal.get('entry_price', 0):,.2f}
   止损: ${signal.get('stop_loss', 0):,.2f}
   止盈: ${signal.get('take_profit', 0):,.2f}
   置信度: {signal.get('confidence', 0):.0%}

"""
                    return {"success": True, "response": response, "data": signals}
                else:
                    return {"success": True, "response": "📭 暂无交易信号\n\n系统正在分析市场，请稍后再查看"}
            
            return {"success": False, "response": "AI交易引擎未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取信号失败: {str(e)}"}
    
    async def _analyze_risk(self) -> Dict[str, Any]:
        """分析风险"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'risk_monitor'):
                monitor = self.main_controller.risk_monitor
                risk_data = await monitor.check_account_risk()
                
                if risk_data:
                    level_emoji = {
                        "low": "🟢",
                        "medium": "🟡",
                        "high": "🟠",
                        "critical": "🔴"
                    }.get(risk_data.risk_level.value, "⚪")
                    
                    warnings_text = "\n".join(risk_data.warnings) if risk_data.warnings else "系统运行正常"
                    
                    return {
                        "success": True,
                        "response": f"""⚠️ 风险评估

风险等级: {level_emoji} {risk_data.risk_level.value.upper()}
保证金比例: {risk_data.margin_ratio*100:.2f}%
未实现盈亏: ${risk_data.unrealized_pnl:+,.2f}
总权益: ${risk_data.total_equity:,.2f}

{warnings_text}""",
                        "data": {
                            "level": risk_data.risk_level.value,
                            "margin_ratio": risk_data.margin_ratio,
                            "unrealized_pnl": risk_data.unrealized_pnl,
                            "total_equity": risk_data.total_equity,
                            "suggestions": warnings_text
                        }
                    }
            
            return {"success": False, "response": "风险监控未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"风险分析失败: {str(e)}"}
    
    async def _execute_trade(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """执行交易"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                
                if self.llm_integration:
                    prompt = f"""解析用户交易指令，返回JSON格式的交易参数：

用户指令：{user_input}

返回格式：
{{
    "action": "buy/sell/hold",
    "symbol": "交易对",
    "quantity": 数量,
    "price": 价格（可选，不填则市价）
}}

只返回JSON。"""
                    
                    response = await self.llm_integration.generate(prompt)
                    if response.success:
                        import json
                        trade_params = json.loads(response.content)
                        
                        return {
                            "success": True,
                            "response": f"""📝 交易指令已解析

操作: {trade_params.get('action', 'N/A').upper()}
交易对: {trade_params.get('symbol', 'N/A')}
数量: {trade_params.get('quantity', 'N/A')}

⚠️ 注意：实盘交易需要确认配置。当前为分析模式。""",
                            "data": trade_params
                        }
                
                return {"success": False, "response": "交易指令解析失败"}
            
            return {"success": False, "response": "AI交易引擎未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"交易执行失败: {str(e)}"}
    
    async def _get_third_party_data(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """获取第三方数据"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'plugin_manager'):
                pm = self.main_controller.plugin_manager
                plugins_info = pm.get_all_plugin_info()
                
                response = "📦 第三方数据源\n\n"
                
                data_plugins = []
                for plugin_name, info in plugins_info.items():
                    plugin_type = info.get('type', 'unknown')
                    if plugin_type == 'data_provider' or 'data' in plugin_name.lower():
                        data_plugins.append({
                            'name': plugin_name,
                            'type': plugin_type,
                            'status': 'running' if info.get('enabled', False) else 'stopped',
                            'description': info.get('description', 'N/A')
                        })
                
                if data_plugins:
                    for plugin in data_plugins:
                        status = "🟢" if plugin.get('status') == 'running' else "🔴"
                        response += f"""{status} {plugin.get('name', 'Unknown')}
   类型: {plugin.get('type', 'N/A')}
   状态: {plugin.get('status', 'N/A')}
   描述: {plugin.get('description', 'N/A')}

"""
                    return {"success": True, "response": response, "data": data_plugins}
                else:
                    return {"success": True, "response": "暂无第三方数据源插件\n\n可以使用插件系统添加数据源。"}
            
            return {"success": False, "response": "插件管理器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取第三方数据失败: {str(e)}"}
    
    async def _get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            if self.main_controller:
                mc = self.main_controller
                
                modules = {
                    "策略管理器": hasattr(mc, 'strategy_manager') and mc.strategy_manager is not None,
                    "AI交易引擎": hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine is not None,
                    "OKX交易所": hasattr(mc, 'okx_exchange') and mc.okx_exchange is not None,
                    "风险监控": hasattr(mc, 'risk_monitor') and mc.risk_monitor is not None,
                    "LLM集成": hasattr(mc, 'llm_integration') and mc.llm_integration is not None,
                    "记忆系统": hasattr(mc, 'ai_memory_manager') and mc.ai_memory_manager is not None,
                    "回测系统": hasattr(mc, 'enhanced_backtester') and mc.enhanced_backtester is not None,
                    "参数优化器": hasattr(mc, 'parameter_optimizer') and mc.parameter_optimizer is not None,
                    "插件管理器": hasattr(mc, 'plugin_manager') and mc.plugin_manager is not None,
                }
                
                response = "🟢 系统状态\n\n"
                for name, status in modules.items():
                    emoji = "✅" if status else "❌"
                    response += f"{emoji} {name}\n"
                
                response += f"\n更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                return {"success": True, "response": response, "data": modules}
            
            return {"success": False, "response": "主控制器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取系统状态失败: {str(e)}"}
    
    async def _general_chat(self, user_input: str) -> Dict[str, Any]:
        """通用对话"""
        try:
            if self.llm_integration:
                system_context = await self._get_system_context()
                
                prompt = f"""你是一个专业的量化交易AI助手。你可以访问以下系统功能：

{system_context}

用户问题：{user_input}

请提供专业、有帮助的回答。如果用户的问题涉及交易、策略、市场分析等，告诉他们可以使用具体命令来获取实时数据。"""
                
                response = await self.llm_integration.generate(prompt)
                
                if response.success:
                    return {
                        "success": True,
                        "response": response.content,
                        "model_id": response.model_id,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return {"success": False, "response": "AI服务暂时不可用"}
            
        except Exception as e:
            return {"success": False, "response": f"对话处理失败: {str(e)}"}
    
    async def _get_system_context(self) -> str:
        """获取系统上下文 - 动态获取实时系统状态"""
        context_parts = []
        
        context_parts.append("=" * 50)
        context_parts.append("【全智能量化交易系统 - 实时状态】")
        context_parts.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        context_parts.append("=" * 50)
        
        if self.main_controller:
            mc = self.main_controller
            
            # 1. 系统模块状态
            context_parts.append("\n📦 【系统模块状态】")
            modules_status = {
                "策略管理器": hasattr(mc, 'strategy_manager') and mc.strategy_manager is not None,
                "AI交易引擎": hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine is not None,
                "OKX交易所": hasattr(mc, 'okx_exchange') and mc.okx_exchange is not None,
                "风险监控": hasattr(mc, 'risk_monitor') and mc.risk_monitor is not None,
                "LLM集成": hasattr(mc, 'llm_integration') and mc.llm_integration is not None,
                "记忆系统": hasattr(mc, 'ai_memory_manager') and mc.ai_memory_manager is not None,
                "Telegram机器人": hasattr(mc, 'telegram_bot') and mc.telegram_bot is not None,
            }
            
            for name, status in modules_status.items():
                status_text = "✅ 运行中" if status else "❌ 未连接"
                context_parts.append(f"  - {name}: {status_text}")
            
            # 2. AI交易引擎状态
            if hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine:
                engine = mc.ai_trading_engine
                engine_status = engine.get_status()
                
                context_parts.append(f"\n🤖 【AI交易引擎状态】")
                context_parts.append(f"  - 运行状态: {'运行中' if engine_status.get('running') else '已停止'}")
                context_parts.append(f"  - 当前状态: {engine_status.get('state', 'unknown')}")
                context_parts.append(f"  - 当前持仓数: {engine_status.get('positions', 0)}")
                context_parts.append(f"  - 历史交易数: {engine_status.get('trade_count', 0)}")
                context_parts.append(f"  - 监控交易对: {', '.join(engine_status.get('symbols', []))}")
                
                ai_config = engine_status.get('ai_config', {})
                if ai_config:
                    context_parts.append(f"  - 最小置信度: {ai_config.get('min_confidence', 0.65)}")
                    context_parts.append(f"  - 最大持仓数: {ai_config.get('max_positions', 3)}")
            
            # 3. 账户和持仓信息（尝试获取）
            context_parts.append(f"\n💰 【账户与持仓】")
            try:
                if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                    balance = await mc.okx_exchange.get_balance()
                    if balance:
                        total = sum(v if isinstance(v, (int, float)) else v.get('free', 0) for v in balance.values())
                        context_parts.append(f"  - 总资产约: ${total:,.2f} USDT")
                        for currency, amount in list(balance.items())[:5]:
                            if isinstance(amount, dict):
                                context_parts.append(f"    {currency}: {amount.get('free', 0):,.4f}")
                            else:
                                context_parts.append(f"    {currency}: {amount:,.4f}")
                    
                    positions = await mc.okx_exchange.get_positions()
                    if positions:
                        context_parts.append(f"\n  📊 当前持仓 ({len(positions)} 个):")
                        for pos in positions[:5]:
                            side_emoji = "🟢多" if pos.get('side') == 'long' else "🔴空"
                            pnl = pos.get('unrealized_pnl', 0)
                            context_parts.append(f"    {side_emoji} {pos.get('symbol')} | 数量:{pos.get('size', 0):.4f} | 盈亏:${pnl:+,.2f}")
                    else:
                        context_parts.append("  - 当前无持仓")
                else:
                    context_parts.append("  - 交易所未连接")
            except Exception as e:
                context_parts.append(f"  - 获取账户信息失败: {str(e)[:50]}")
            
            # 4. 策略信息
            if hasattr(mc, 'strategy_manager') and mc.strategy_manager:
                sm = mc.strategy_manager
                strategy_count = len(sm.strategy_configs)
                instance_count = len(sm.strategy_instances)
                
                context_parts.append(f"\n📋 【策略管理】")
                context_parts.append(f"  - 已注册策略: {strategy_count} 个")
                context_parts.append(f"  - 运行实例: {instance_count} 个")
                
                if sm.strategy_configs:
                    context_parts.append("  - 策略列表:")
                    for sid, config in list(sm.strategy_configs.items())[:5]:
                        enabled = "启用" if config.enabled else "禁用"
                        context_parts.append(f"    • {config.name} [{enabled}]")
            
            # 5. 风险监控状态
            if hasattr(mc, 'risk_monitor') and mc.risk_monitor:
                risk_status = mc.risk_monitor.get_status()
                last_check = risk_status.get('last_check', {})
                
                context_parts.append(f"\n⚠️ 【风险监控】")
                context_parts.append(f"  - 监控状态: {'运行中' if risk_status.get('running') else '已停止'}")
                if last_check:
                    context_parts.append(f"  - 风险等级: {last_check.get('risk_level', 'unknown').upper()}")
                    context_parts.append(f"  - 保证金比例: {last_check.get('margin_ratio', 0)*100:.1f}%")
        
        # 可用功能说明
        context_parts.append("\n" + "=" * 50)
        context_parts.append("【可用功能命令】")
        context_parts.append("=" * 50)
        context_parts.append("""
• "查看策略列表" / "策略管理" - 查看所有注册的策略
• "创建策略 [描述]" - 使用AI生成新策略
• "回测策略 [天数]" - 运行策略回测测试
• "市场分析 BTC/ETH" - 分析指定交易对市场
• "查看行情 BTC" - 获取实时行情数据
• "账户余额" - 查看账户资金状况
• "查看持仓" - 显示当前所有持仓
• "交易信号" - 查看最新AI交易信号
• "风险评估" - 分析当前账户风险
• "系统状态" - 查看系统运行状态
• "优化策略" - 自动优化策略参数
""")
        
        return "\n".join(context_parts)
    
    async def _combine_strategies(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """组合多个策略 - AI自主决定组合方式"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                available_strategies = list(sm.strategy_configs.keys())
                
                if self.llm_integration:
                    prompt = f"""用户想要组合策略。

可用策略: {available_strategies}
用户输入: {user_input}

请分析用户意图，决定：
1. 选择哪些策略组合
2. 各策略的权重分配
3. 组合逻辑（并行、串行、投票等）

返回JSON格式：
{{
    "strategies": ["策略ID列表"],
    "weights": {{"策略ID": 权重}},
    "combination_mode": "parallel/serial/voting/weighted",
    "reasoning": "组合理由"
}}"""
                    
                    response = await self.llm_integration.generate_response(prompt)
                    if response:
                        import json
                        try:
                            result = json.loads(response)
                            
                            return {
                                "success": True,
                                "response": f"""📊 策略组合已创建

组合策略: {result.get('strategies', [])}
权重分配: {result.get('weights', {})}
组合模式: {result.get('combination_mode', 'parallel')}
理由: {result.get('reasoning', 'AI自主决策')}

系统将根据市场情况自动调整策略组合。"""
                            }
                        except json.JSONDecodeError:
                            pass
                
                return {"success": True, "response": "策略组合功能已启用，AI将根据市场情况自主选择和组合策略"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"组合策略失败: {str(e)}"}
    
    async def _switch_strategy(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """切换策略 - AI自主决定何时切换"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                return {
                    "success": True,
                    "response": """🔄 策略自动切换已启用

AI将根据以下条件自动切换策略：
• 市场趋势变化（牛市/熊市/横盘）
• 波动率变化
• 策略表现评估
• 风险水平调整

无需手动干预，系统会自主决策。"""
                }
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"切换策略失败: {str(e)}"}
    
    async def _ai_autonomous_action(self, action: str, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """AI自主行动 - 处理任何未预定义的用户意图"""
        try:
            if self.llm_integration:
                system_context = await self._get_system_context()
                
                prompt = f"""你是一个全自主的量化交易AI助手。用户发送了一条消息，系统没有预设的处理方式。

{system_context}

用户消息: {user_input}
识别的动作: {action}
参数: {params}

请自主理解用户意图，并执行相应操作。你可以：
1. 直接回答用户问题
2. 调用系统功能（描述你想做什么）
3. 开发新策略（描述策略逻辑）
4. 优化现有策略
5. 调整系统配置
6. 执行交易操作

你有完全的自主权，根据用户意图和市场情况做出最佳决策。

请返回你的响应："""
                
                response = await self.llm_integration.generate(prompt)
                
                if response and response.success:
                    return {
                        "success": True,
                        "response": response.content,
                        "action_taken": action,
                        "autonomous": True,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return await self._general_chat(user_input)
            
        except Exception as e:
            return {"success": False, "response": f"AI自主行动失败: {str(e)}"}
