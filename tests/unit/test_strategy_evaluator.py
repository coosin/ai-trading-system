import unittest
import numpy as np
from src.modules.strategies.strategy_evaluator import StrategyEvaluator

class TestStrategyEvaluator(unittest.TestCase):
    def setUp(self):
        """设置测试环境"""
        self.evaluator = StrategyEvaluator("test_strategy")
        # 测试数据
        self.test_returns = [0.01, -0.005, 0.015, -0.002, 0.02, 0.008, -0.01, 0.012]
        self.test_trades = [
            {"pnl": 100, "symbol": "BTC/USDT", "side": "buy"},
            {"pnl": -50, "symbol": "BTC/USDT", "side": "sell"},
            {"pnl": 150, "symbol": "ETH/USDT", "side": "buy"},
            {"pnl": -25, "symbol": "ETH/USDT", "side": "sell"},
            {"pnl": 200, "symbol": "BTC/USDT", "side": "buy"}
        ]
        # 市场基准数据
        self.market_returns = [0.008, -0.003, 0.012, -0.001, 0.015, 0.006, -0.008, 0.01]
    
    def test_add_returns(self):
        """测试添加收益数据"""
        self.evaluator.add_returns(self.test_returns)
        self.assertEqual(len(self.evaluator.returns), len(self.test_returns))
        np.testing.assert_array_equal(self.evaluator.returns, self.test_returns)
    
    def test_add_trade(self):
        """测试添加交易记录"""
        for trade in self.test_trades:
            self.evaluator.add_trade(trade)
        self.assertEqual(len(self.evaluator.trades), len(self.test_trades))
        self.assertEqual(len(self.evaluator.returns), len(self.test_trades))
        expected_returns = [trade["pnl"] for trade in self.test_trades]
        np.testing.assert_array_equal(self.evaluator.returns, expected_returns)
    
    def test_calculate_total_return(self):
        """测试计算总收益"""
        self.evaluator.add_returns(self.test_returns)
        total_return = self.evaluator.calculate_total_return()
        expected_total_return = sum(self.test_returns)
        self.assertAlmostEqual(total_return, expected_total_return)
    
    def test_calculate_annual_return(self):
        """测试计算年化收益"""
        self.evaluator.add_returns(self.test_returns)
        annual_return = self.evaluator.calculate_annual_return()
        # 验证返回值类型和范围
        self.assertIsInstance(annual_return, float)
    
    def test_calculate_sharpe_ratio(self):
        """测试计算夏普比率"""
        self.evaluator.add_returns(self.test_returns)
        sharpe_ratio = self.evaluator.calculate_sharpe_ratio()
        # 验证返回值类型
        self.assertIsInstance(sharpe_ratio, float)
    
    def test_calculate_sortino_ratio(self):
        """测试计算索提诺比率"""
        self.evaluator.add_returns(self.test_returns)
        sortino_ratio = self.evaluator.calculate_sortino_ratio()
        # 验证返回值类型
        self.assertIsInstance(sortino_ratio, float)
    
    def test_calculate_max_drawdown(self):
        """测试计算最大回撤"""
        self.evaluator.add_returns(self.test_returns)
        max_drawdown = self.evaluator.calculate_max_drawdown()
        # 验证返回值类型和范围
        self.assertIsInstance(max_drawdown, float)
        self.assertGreaterEqual(max_drawdown, 0)
    
    def test_calculate_calmar_ratio(self):
        """测试计算卡玛比率"""
        self.evaluator.add_returns(self.test_returns)
        calmar_ratio = self.evaluator.calculate_calmar_ratio()
        # 验证返回值类型
        self.assertIsInstance(calmar_ratio, (float, int))
    
    def test_calculate_win_rate(self):
        """测试计算胜率"""
        self.evaluator.add_returns(self.test_returns)
        win_rate = self.evaluator.calculate_win_rate()
        # 验证返回值类型和范围
        self.assertIsInstance(win_rate, float)
        self.assertGreaterEqual(win_rate, 0)
        self.assertLessEqual(win_rate, 1)
    
    def test_calculate_profit_factor(self):
        """测试计算盈利因子"""
        self.evaluator.add_returns(self.test_returns)
        profit_factor = self.evaluator.calculate_profit_factor()
        # 验证返回值类型
        self.assertIsInstance(profit_factor, (float, int))
    
    def test_calculate_avg_win_loss_ratio(self):
        """测试计算平均盈亏比"""
        self.evaluator.add_returns(self.test_returns)
        avg_win_loss_ratio = self.evaluator.calculate_avg_win_loss_ratio()
        # 验证返回值类型
        self.assertIsInstance(avg_win_loss_ratio, float)
    
    def test_calculate_omega_ratio(self):
        """测试计算欧米茄比率"""
        self.evaluator.add_returns(self.test_returns)
        omega_ratio = self.evaluator.calculate_omega_ratio()
        # 验证返回值类型
        self.assertIsInstance(omega_ratio, (float, int))
    
    def test_calculate_alpha_beta(self):
        """测试计算Alpha和Beta"""
        self.evaluator.add_returns(self.test_returns)
        alpha, beta = self.evaluator.calculate_alpha_beta(self.market_returns)
        # 验证返回值类型
        self.assertIsInstance(alpha, float)
        self.assertIsInstance(beta, float)
    
    def test_calculate_information_ratio(self):
        """测试计算信息比率"""
        self.evaluator.add_returns(self.test_returns)
        info_ratio = self.evaluator.calculate_information_ratio(self.market_returns)
        # 验证返回值类型
        self.assertIsInstance(info_ratio, float)
    
    def test_calculate_kurtosis(self):
        """测试计算峰度"""
        self.evaluator.add_returns(self.test_returns)
        kurtosis = self.evaluator.calculate_kurtosis()
        # 验证返回值类型
        self.assertIsInstance(kurtosis, float)
    
    def test_calculate_skewness(self):
        """测试计算偏度"""
        self.evaluator.add_returns(self.test_returns)
        skewness = self.evaluator.calculate_skewness()
        # 验证返回值类型
        self.assertIsInstance(skewness, float)
    
    def test_get_evaluation_report(self):
        """测试获取评估报告"""
        self.evaluator.add_returns(self.test_returns)
        for trade in self.test_trades:
            self.evaluator.add_trade(trade)
        
        # 基本报告
        report = self.evaluator.get_evaluation_report()
        self.assertIsInstance(report, dict)
        self.assertIn("strategy_name", report)
        self.assertIn("total_trades", report)
        self.assertIn("total_return", report)
        self.assertIn("annual_return", report)
        self.assertIn("sharpe_ratio", report)
        self.assertIn("max_drawdown", report)
        self.assertIn("win_rate", report)
        
        # 带市场基准的报告
        report_with_benchmark = self.evaluator.get_evaluation_report(market_returns=self.market_returns)
        self.assertIn("alpha", report_with_benchmark)
        self.assertIn("beta", report_with_benchmark)
    
    def test_get_risk_metrics(self):
        """测试获取风险指标"""
        self.evaluator.add_returns(self.test_returns)
        risk_metrics = self.evaluator.get_risk_metrics()
        self.assertIsInstance(risk_metrics, dict)
        self.assertIn("volatility", risk_metrics)
        self.assertIn("value_at_risk", risk_metrics)
        self.assertIn("conditional_value_at_risk", risk_metrics)
        self.assertIn("max_drawdown", risk_metrics)
    
    def test_get_performance_metrics(self):
        """测试获取性能指标"""
        self.evaluator.add_returns(self.test_returns)
        performance_metrics = self.evaluator.get_performance_metrics()
        self.assertIsInstance(performance_metrics, dict)
        self.assertIn("total_return", performance_metrics)
        self.assertIn("annual_return", performance_metrics)
        self.assertIn("sharpe_ratio", performance_metrics)
        self.assertIn("sortino_ratio", performance_metrics)
        self.assertIn("calmar_ratio", performance_metrics)
    
    def test_get_trade_metrics(self):
        """测试获取交易指标"""
        for trade in self.test_trades:
            self.evaluator.add_trade(trade)
        trade_metrics = self.evaluator.get_trade_metrics()
        self.assertIsInstance(trade_metrics, dict)
        self.assertIn("total_trades", trade_metrics)
        self.assertIn("win_rate", trade_metrics)
        self.assertIn("profit_factor", trade_metrics)
        self.assertIn("avg_win_loss_ratio", trade_metrics)
    
    def test_empty_returns(self):
        """测试空收益数据的情况"""
        # 测试各种方法在空收益情况下的表现
        self.assertEqual(self.evaluator.calculate_total_return(), 0)
        self.assertEqual(self.evaluator.calculate_annual_return(), 0)
        self.assertEqual(self.evaluator.calculate_sharpe_ratio(), 0)
        self.assertEqual(self.evaluator.calculate_sortino_ratio(), 0)
        self.assertEqual(self.evaluator.calculate_max_drawdown(), 0)
        self.assertEqual(self.evaluator.calculate_win_rate(), 0)
        self.assertEqual(self.evaluator.calculate_profit_factor(), 0)
        self.assertEqual(self.evaluator.calculate_avg_win_loss_ratio(), 0)
        self.assertEqual(self.evaluator.calculate_omega_ratio(), 0)
        self.assertEqual(self.evaluator.calculate_kurtosis(), 0)
        self.assertEqual(self.evaluator.calculate_skewness(), 0)
        self.assertEqual(self.evaluator.calculate_alpha_beta(self.market_returns), (0, 0))
        self.assertEqual(self.evaluator.calculate_information_ratio(self.market_returns), 0)

if __name__ == '__main__':
    unittest.main()