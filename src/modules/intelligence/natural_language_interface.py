import json
import logging
from typing import Dict, Any, Optional

from src.modules.core.llm_integration import EnhancedLLMIntegration

logger = logging.getLogger(__name__)

class NaturalLanguageInterface:
    def __init__(self, llm_integration: EnhancedLLMIntegration):
        """
        初始化自然语言接口

        Args:
            llm_integration: 大模型集成实例
        """
        self.llm_integration = llm_integration
        self.command_templates = {
            "get_system_status": {
                "description": "获取系统状态",
                "keywords": ["系统状态", "运行状态", "健康状态", "系统信息"],
                "function": "get_system_status"
            },
            "get_strategy_performance": {
                "description": "获取策略性能",
                "keywords": ["策略性能", "策略表现", "收益情况", "策略统计"],
                "function": "get_strategy_performance"
            },
            "analyze_market": {
                "description": "分析市场",
                "keywords": ["市场分析", "行情分析", "市场趋势", "市场预测"],
                "function": "analyze_market"
            },
            "generate_strategy": {
                "description": "生成策略",
                "keywords": ["生成策略", "创建策略", "推荐策略", "策略建议"],
                "function": "generate_strategy"
            },
            "evaluate_strategy": {
                "description": "评估策略",
                "keywords": ["评估策略", "策略评价", "策略分析", "策略指标"],
                "function": "evaluate_strategy"
            },
            "run_backtest": {
                "description": "运行回测",
                "keywords": ["回测", "历史测试", "模拟测试", "回测结果"],
                "function": "run_backtest"
            },
            "get_market_data": {
                "description": "获取市场数据",
                "keywords": ["市场数据", "行情数据", "价格数据", "K线数据"],
                "function": "get_market_data"
            },
            "get_portfolio_analysis": {
                "description": "获取投资组合分析",
                "keywords": ["投资组合", "资产配置", "组合分析", "风险分析"],
                "function": "get_portfolio_analysis"
            },
            "optimize_parameters": {
                "description": "优化策略参数",
                "keywords": ["参数优化", "调优", "优化参数", "参数调整"],
                "function": "optimize_parameters"
            },
            "get_alert_history": {
                "description": "获取告警历史",
                "keywords": ["告警历史", "预警记录", "异常记录", "告警信息"],
                "function": "get_alert_history"
            }
        }
    
    async def process_query(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理自然语言查询

        Args:
            query: 自然语言查询
            context: 上下文信息

        Returns:
            处理结果
        """
        try:
            # 识别查询类型
            command = await self._identify_command(query)
            
            if command:
                # 执行命令
                result = await self._execute_command(command, query, context)
                return result
            else:
                # 通用问答
                return await self._general_qa(query, context)
        except Exception as e:
            logger.error(f"处理自然语言查询时出错: {e}")
            return {
                "error": str(e),
                "message": "处理查询时发生错误"
            }
    
    async def _identify_command(self, query: str) -> Optional[str]:
        """
        识别查询对应的命令

        Args:
            query: 自然语言查询

        Returns:
            命令名称
        """
        # 使用大模型识别命令
        prompt = f"""请从以下命令中识别用户查询 '{query}' 对应的命令：

可用命令：
{chr(10).join([f"- {cmd}: {info['description']}" for cmd, info in self.command_templates.items()])}

如果没有匹配的命令，请返回 'unknown'。

只返回命令名称，不要返回其他内容。"""
        
        response = await self.llm_integration.generate(prompt)
        command = response.strip() if response else 'unknown'
        
        if command not in self.command_templates and command != 'unknown':
            command = 'unknown'
        
        logger.debug(f"识别命令: {query} -> {command}")
        return command
    
    async def _execute_command(self, command: str, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行命令

        Args:
            command: 命令名称
            query: 原始查询
            context: 上下文信息

        Returns:
            命令执行结果
        """
        if command not in self.command_templates:
            return {
                "error": "命令不存在",
                "message": f"未知命令: {command}"
            }
        
        # 提取命令参数
        params = await self._extract_parameters(command, query, context)
        
        # 构建命令执行提示
        prompt = f"""请执行以下命令并返回结果：

命令: {command}
描述: {self.command_templates[command]['description']}
参数: {json.dumps(params, ensure_ascii=False)}

请以JSON格式返回执行结果，包含以下字段：
- success: 是否成功
- data: 执行结果数据
- message: 执行消息
- details: 详细信息（可选）"""
        
        response = await self.llm_integration.generate(prompt)
        
        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            result = {
                "success": False,
                "data": None,
                "message": "命令执行失败",
                "details": f"无法解析命令执行结果: {response}"
            }
        
        return result
    
    async def _extract_parameters(self, command: str, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        提取命令参数

        Args:
            command: 命令名称
            query: 原始查询
            context: 上下文信息

        Returns:
            命令参数
        """
        prompt = f"""请从查询 '{query}' 中提取命令 '{command}' 的参数：

命令描述: {self.command_templates[command]['description']}

请以JSON格式返回提取的参数，只返回参数，不要返回其他内容。
如果没有参数，请返回空对象 {}。"""
        
        response = await self.llm_integration.generate(prompt)
        
        try:
            params = json.loads(response)
        except json.JSONDecodeError:
            params = {}
        
        return params
    
    async def _general_qa(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        通用问答

        Args:
            query: 自然语言查询
            context: 上下文信息

        Returns:
            问答结果
        """
        prompt = f"""请回答用户的问题：

问题: {query}

请以JSON格式返回回答，包含以下字段：
- answer: 回答内容
- confidence: 置信度（0-1）
- source: 回答来源
- related_commands: 相关命令（可选）"""
        
        response = await self.llm_integration.generate(prompt)
        
        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            result = {
                "answer": response,
                "confidence": 0.8,
                "source": "llm",
                "related_commands": []
            }
        
        return result
    
    async def generate_response(self, result: Dict[str, Any], query: str) -> str:
        """
        生成自然语言响应

        Args:
            result: 命令执行结果
            query: 原始查询

        Returns:
            自然语言响应
        """
        prompt = f"""请根据以下执行结果，生成一个自然友好的回答，回复用户的查询 '{query}'：

执行结果: {json.dumps(result, ensure_ascii=False)}

请直接返回回答内容，不要包含任何格式标记。"""
        
        response = await self.llm_integration.generate(prompt)
        return response
    
    async def process_and_respond(self, query: str, context: Dict[str, Any] = None) -> str:
        """
        处理查询并生成响应

        Args:
            query: 自然语言查询
            context: 上下文信息

        Returns:
            自然语言响应
        """
        result = await self.process_query(query, context)
        response = await self.generate_response(result, query)
        return response
    
    def get_available_commands(self) -> Dict[str, Dict[str, Any]]:
        """
        获取可用命令

        Returns:
            可用命令列表
        """
        return self.command_templates
    
    def add_command(self, command_name: str, description: str, keywords: list, function: str) -> bool:
        """
        添加新命令

        Args:
            command_name: 命令名称
            description: 命令描述
            keywords: 关键词列表
            function: 关联函数

        Returns:
            是否添加成功
        """
        if command_name in self.command_templates:
            return False
        
        self.command_templates[command_name] = {
            "description": description,
            "keywords": keywords,
            "function": function
        }
        return True
    
    def remove_command(self, command_name: str) -> bool:
        """
        删除命令

        Args:
            command_name: 命令名称

        Returns:
            是否删除成功
        """
        if command_name in self.command_templates:
            del self.command_templates[command_name]
            return True
        return False