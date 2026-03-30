import unittest
from unittest.mock import Mock, AsyncMock
from src.modules.intelligence.natural_language_interface import NaturalLanguageInterface

class TestNaturalLanguageInterface(unittest.TestCase):
    def setUp(self):
        """设置测试环境"""
        # 创建模拟的大模型集成实例
        self.mock_llm = Mock(spec=['generate'])
        self.mock_llm.generate = AsyncMock()
        
        # 创建自然语言接口实例
        self.nli = NaturalLanguageInterface(self.mock_llm)
    
    async def test_identify_command(self):
        """测试命令识别"""
        # 模拟大模型返回
        self.mock_llm.generate.return_value = "get_system_status"
        
        # 测试命令识别
        query = "系统现在的运行状态如何？"
        command = await self.nli._identify_command(query)
        
        self.assertEqual(command, "get_system_status")
        self.mock_llm.generate.assert_called_once()
    
    async def test_identify_unknown_command(self):
        """测试识别未知命令"""
        # 模拟大模型返回
        self.mock_llm.generate.return_value = "unknown"
        
        # 测试命令识别
        query = "这是一个与系统无关的问题"
        command = await self.nli._identify_command(query)
        
        self.assertEqual(command, "unknown")
    
    async def test_extract_parameters(self):
        """测试参数提取"""
        # 模拟大模型返回
        self.mock_llm.generate.return_value = '{"symbol": "BTC/USDT", "timeframe": "1h"}'
        
        # 测试参数提取
        command = "get_market_data"
        query = "获取比特币的1小时K线数据"
        params = await self.nli._extract_parameters(command, query)
        
        self.assertIsInstance(params, dict)
        self.assertEqual(params.get("symbol"), "BTC/USDT")
        self.assertEqual(params.get("timeframe"), "1h")
    
    async def test_extract_parameters_invalid_json(self):
        """测试提取参数时遇到无效JSON的情况"""
        # 模拟大模型返回无效JSON
        self.mock_llm.generate.return_value = "这不是有效的JSON"
        
        # 测试参数提取
        command = "get_market_data"
        query = "获取比特币的K线数据"
        params = await self.nli._extract_parameters(command, query)
        
        self.assertEqual(params, {})
    
    async def test_execute_command(self):
        """测试命令执行"""
        # 模拟大模型返回
        self.mock_llm.generate.side_effect = [
            '{"symbol": "BTC/USDT"}',  # 参数提取
            '{"success": true, "data": {"price": 50000}, "message": "获取成功"}'  # 命令执行
        ]
        
        # 测试命令执行
        command = "get_market_data"
        query = "比特币的价格是多少？"
        result = await self.nli._execute_command(command, query)
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("data").get("price"), 50000)
    
    async def test_execute_command_invalid_json(self):
        """测试命令执行时遇到无效JSON的情况"""
        # 模拟大模型返回
        self.mock_llm.generate.side_effect = [
            '{}',  # 参数提取
            '这不是有效的JSON'  # 命令执行
        ]
        
        # 测试命令执行
        command = "get_system_status"
        query = "系统状态如何？"
        result = await self.nli._execute_command(command, query)
        
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("success"))
        self.assertIn("无法解析命令执行结果", result.get("details", ""))
    
    async def test_execute_unknown_command(self):
        """测试执行未知命令"""
        # 测试执行未知命令
        command = "unknown_command"
        query = "测试未知命令"
        result = await self.nli._execute_command(command, query)
        
        self.assertIsInstance(result, dict)
        self.assertIn("命令不存在", result.get("error", ""))
    
    async def test_general_qa(self):
        """测试通用问答"""
        # 模拟大模型返回
        self.mock_llm.generate.return_value = '{"answer": "这是一个测试回答", "confidence": 0.9, "source": "llm"}'
        
        # 测试通用问答
        query = "什么是量化交易？"
        result = await self.nli._general_qa(query)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("answer"), "这是一个测试回答")
        self.assertEqual(result.get("confidence"), 0.9)
        self.assertEqual(result.get("source"), "llm")
    
    async def test_general_qa_invalid_json(self):
        """测试通用问答时遇到无效JSON的情况"""
        # 模拟大模型返回无效JSON
        self.mock_llm.generate.return_value = "这是一个测试回答"
        
        # 测试通用问答
        query = "什么是量化交易？"
        result = await self.nli._general_qa(query)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("answer"), "这是一个测试回答")
        self.assertEqual(result.get("confidence"), 0.8)
        self.assertEqual(result.get("source"), "llm")
    
    async def test_generate_response(self):
        """测试生成自然语言响应"""
        # 模拟大模型返回
        self.mock_llm.generate.return_value = "系统运行正常，所有模块都在正常工作。"
        
        # 测试生成响应
        result = {"success": True, "data": {"status": "healthy"}, "message": "获取系统状态成功"}
        query = "系统状态如何？"
        response = await self.nli.generate_response(result, query)
        
        self.assertEqual(response, "系统运行正常，所有模块都在正常工作。")
    
    async def test_process_query_command(self):
        """测试处理命令类型的查询"""
        # 模拟大模型返回
        self.mock_llm.generate.side_effect = [
            "get_system_status",  # 命令识别
            '{}',  # 参数提取
            '{"success": true, "data": {"status": "healthy"}, "message": "获取成功"}'  # 命令执行
        ]
        
        # 测试处理查询
        query = "系统状态如何？"
        result = await self.nli.process_query(query)
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success"))
    
    async def test_process_query_general(self):
        """测试处理通用查询"""
        # 模拟大模型返回
        self.mock_llm.generate.side_effect = [
            "unknown",  # 命令识别
            '{"answer": "这是一个测试回答", "confidence": 0.9, "source": "llm"}'  # 通用问答
        ]
        
        # 测试处理查询
        query = "什么是量化交易？"
        result = await self.nli.process_query(query)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("answer"), "这是一个测试回答")
    
    async def test_process_and_respond(self):
        """测试处理查询并生成响应"""
        # 模拟大模型返回
        self.mock_llm.generate.side_effect = [
            "get_system_status",  # 命令识别
            '{}',  # 参数提取
            '{"success": true, "data": {"status": "healthy"}, "message": "获取成功"}',  # 命令执行
            "系统运行正常，所有模块都在正常工作。"  # 生成响应
        ]
        
        # 测试处理并响应
        query = "系统状态如何？"
        response = await self.nli.process_and_respond(query)
        
        self.assertEqual(response, "系统运行正常，所有模块都在正常工作。")
    
    def test_get_available_commands(self):
        """测试获取可用命令"""
        commands = self.nli.get_available_commands()
        self.assertIsInstance(commands, dict)
        self.assertIn("get_system_status", commands)
        self.assertIn("get_strategy_performance", commands)
        self.assertIn("analyze_market", commands)
    
    def test_add_command(self):
        """测试添加新命令"""
        # 测试添加新命令
        success = self.nli.add_command(
            "test_command",
            "测试命令",
            ["测试", "测试命令"],
            "test_function"
        )
        self.assertTrue(success)
        
        # 验证命令已添加
        commands = self.nli.get_available_commands()
        self.assertIn("test_command", commands)
        self.assertEqual(commands["test_command"]["description"], "测试命令")
    
    def test_add_existing_command(self):
        """测试添加已存在的命令"""
        # 测试添加已存在的命令
        success = self.nli.add_command(
            "get_system_status",
            "测试命令",
            ["测试"],
            "test_function"
        )
        self.assertFalse(success)
    
    def test_remove_command(self):
        """测试删除命令"""
        # 先添加一个测试命令
        self.nli.add_command(
            "test_command",
            "测试命令",
            ["测试"],
            "test_function"
        )
        
        # 测试删除命令
        success = self.nli.remove_command("test_command")
        self.assertTrue(success)
        
        # 验证命令已删除
        commands = self.nli.get_available_commands()
        self.assertNotIn("test_command", commands)
    
    def test_remove_nonexistent_command(self):
        """测试删除不存在的命令"""
        # 测试删除不存在的命令
        success = self.nli.remove_command("nonexistent_command")
        self.assertFalse(success)

if __name__ == '__main__':
    unittest.main()