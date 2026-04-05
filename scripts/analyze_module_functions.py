#!/usr/bin/env python3
"""
模块功能全面排查工具

功能：
1. 扫描所有正在使用的模块
2. 分析每个模块的具体功能
3. 识别重复或相似的功能
4. 检查命名规范性
5. 生成规范化建议
"""

import os
import re
import ast
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

class ModuleFunctionAnalyzer:
    """模块功能分析器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.modules_dir = self.base_path / "src" / "modules"
        
        # 主控制器中实际使用的模块
        self.active_modules = {
            # 核心系统
            "event_system": "EnhancedEventSystem",
            "data_quality_system": "EnhancedDataQualitySystem",
            "fault_tolerance": "EnhancedFaultTolerance",
            "llm_integration": "EnhancedLLMIntegration",
            "enhanced_llm_manager": "EnhancedLLMManager",
            "plugin_manager": "PluginManager",
            "database_manager": "DatabaseManager",
            "business_process_manager": "BusinessProcessManager",
            "unified_memory": "UnifiedMemorySystem",
            "strategy_manager": "StrategyManager",
            
            # 智能系统
            "hierarchical_memory": "HierarchicalMemoryManager",
            "skill_manager": "SkillManager",
            "heartbeat_monitor": "HeartbeatMonitor",
            "smart_notification": "SmartNotificationSystem",
            
            # 信息收集
            "unified_info_collector": "UnifiedInfoCollector",
            
            # 监控和通知
            "trading_monitor": "TradingMonitor",
            "telegram_bot": "TelegramBot",
            "anomaly_detector": "AnomalyDetector",
            
            # 策略和优化
            "portfolio_optimizer": "PortfolioOptimizer",
            "parameter_optimizer": "ParameterOptimizer",
            "strategy_evaluator": "StrategyEvaluator",
            
            # 回测和数据
            "enhanced_backtester": "BacktestEngine",
            "data_storage": "EnhancedDataStorage",
            "backup_manager": "DataBackupManager",
            
            # AI和交易
            "ai_trading_engine": "AITradingEngine",
            "ai_core": "AICoreDecisionEngine",
            "natural_language_interface": "NaturalLanguageInterface",
            
            # 模拟
            "simulated_market": "SimulatedMarket",
        }
        
        # 功能关键词映射
        self.function_keywords = {
            "数据管理": ["data", "storage", "backup", "database", "cache"],
            "记忆管理": ["memory", "mem", "remember", "recall"],
            "风险管理": ["risk", "safety", "security", "emergency"],
            "交易执行": ["trade", "execution", "order", "position"],
            "策略管理": ["strategy", "strat", "portfolio", "parameter"],
            "监控告警": ["monitor", "alert", "notification", "heartbeat"],
            "API服务": ["api", "server", "endpoint"],
            "LLM集成": ["llm", "language", "model", "gpt"],
            "事件系统": ["event", "message", "bus"],
            "插件系统": ["plugin", "extension", "module"],
            "回测系统": ["backtest", "simulation", "test"],
            "优化系统": ["optim", "tune", "adjust"],
            "分析系统": ["analy", "detect", "assess"],
        }
        
        # 分析结果
        self.analysis_results = {
            "module_functions": {},
            "duplicate_functions": defaultdict(list),
            "similar_modules": defaultdict(list),
            "naming_issues": [],
            "recommendations": []
        }
    
    def analyze_all_modules(self):
        """分析所有模块"""
        print("=" * 80)
        print("🔍 开始全面模块功能分析")
        print("=" * 80)
        
        # 1. 分析每个模块的功能
        print("\n📋 阶段1：分析模块功能")
        print("-" * 80)
        self._analyze_module_functions()
        
        # 2. 识别重复功能
        print("\n📋 阶段2：识别重复功能")
        print("-" * 80)
        self._identify_duplicate_functions()
        
        # 3. 检查命名规范
        print("\n📋 阶段3：检查命名规范")
        print("-" * 80)
        self._check_naming_conventions()
        
        # 4. 生成建议
        print("\n📋 阶段4：生成优化建议")
        print("-" * 80)
        self._generate_recommendations()
        
        # 5. 打印报告
        self._print_report()
    
    def _analyze_module_functions(self):
        """分析每个模块的功能"""
        for module_key, class_name in self.active_modules.items():
            module_file = self._find_module_file(module_key, class_name)
            
            if module_file:
                functions = self._extract_module_functions(module_file, class_name)
                self.analysis_results["module_functions"][module_key] = {
                    "class_name": class_name,
                    "file": str(module_file.relative_to(self.base_path)),
                    "functions": functions,
                    "function_count": len(functions)
                }
                
                print(f"  ✅ {module_key:30s} - {len(functions)} 个方法")
            else:
                print(f"  ⚠️ {module_key:30s} - 文件未找到")
    
    def _find_module_file(self, module_key: str, class_name: str) -> Path:
        """查找模块文件"""
        # 尝试多种可能的文件名
        possible_names = [
            f"{module_key}.py",
            f"{class_name.lower()}.py",
            f"{module_key.replace('_', '')}.py",
        ]
        
        for name in possible_names:
            for py_file in self.modules_dir.rglob(name):
                return py_file
        
        # 如果找不到，搜索包含类名的文件
        for py_file in self.modules_dir.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if f"class {class_name}" in content:
                        return py_file
            except:
                pass
        
        return None
    
    def _extract_module_functions(self, module_file: Path, class_name: str) -> List[str]:
        """提取模块的功能方法"""
        functions = []
        
        try:
            with open(module_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取类中的所有方法
            class_pattern = rf"class {class_name}.*?(?=\nclass |\Z)"
            class_match = re.search(class_pattern, content, re.DOTALL)
            
            if class_match:
                class_content = class_match.group(0)
                
                # 提取所有方法定义
                method_pattern = r"(?:async\s+)?def\s+(\w+)\s*\("
                methods = re.findall(method_pattern, class_content)
                
                # 过滤掉私有方法和特殊方法
                functions = [
                    m for m in methods 
                    if not m.startswith('_') and m not in ['initialize', 'cleanup', 'start', 'stop']
                ]
        
        except Exception as e:
            print(f"    ⚠️ 提取方法失败: {e}")
        
        return functions
    
    def _identify_duplicate_functions(self):
        """识别重复的功能"""
        # 按功能分类
        function_modules = defaultdict(list)
        
        for module_key, info in self.analysis_results["module_functions"].items():
            for func in info["functions"]:
                # 检查功能关键词
                for func_type, keywords in self.function_keywords.items():
                    if any(kw in func.lower() for kw in keywords):
                        function_modules[func_type].append({
                            "module": module_key,
                            "function": func
                        })
        
        # 找出重复的功能
        for func_type, modules in function_modules.items():
            if len(modules) > 1:
                self.analysis_results["duplicate_functions"][func_type] = modules
                print(f"\n  🔍 {func_type}:")
                for item in modules:
                    print(f"      - {item['module']:30s} -> {item['function']}")
    
    def _check_naming_conventions(self):
        """检查命名规范"""
        issues = []
        
        for module_key, info in self.analysis_results["module_functions"].items():
            # 检查类名规范
            class_name = info["class_name"]
            
            # 1. 检查是否以大写字母开头
            if not class_name[0].isupper():
                issues.append(f"{module_key}: 类名 '{class_name}' 应该以大写字母开头")
            
            # 2. 检查是否有过长的名称
            if len(class_name) > 30:
                issues.append(f"{module_key}: 类名 '{class_name}' 过长 ({len(class_name)} 字符)")
            
            # 3. 检查是否有重复的前缀
            if class_name.count("Enhanced") > 1:
                issues.append(f"{module_key}: 类名 '{class_name}' 有重复的 'Enhanced' 前缀")
            
            # 4. 检查方法命名
            for func in info["functions"]:
                # 检查是否使用驼峰命名
                if '_' in func and func[0].islower():
                    # 这是snake_case，是好的
                    pass
                elif func[0].isupper():
                    issues.append(f"{module_key}: 方法 '{func}' 应该使用 snake_case 命名")
        
        self.analysis_results["naming_issues"] = issues
        
        if issues:
            print(f"\n  ⚠️ 发现 {len(issues)} 个命名问题:")
            for issue in issues[:10]:
                print(f"      - {issue}")
        else:
            print("\n  ✅ 命名规范检查通过")
    
    def _generate_recommendations(self):
        """生成优化建议"""
        recommendations = []
        
        # 1. 基于重复功能的建议
        if self.analysis_results["duplicate_functions"]:
            for func_type, modules in self.analysis_results["duplicate_functions"].items():
                if len(modules) > 2:
                    recommendations.append({
                        "type": "整合",
                        "priority": "高",
                        "description": f"{func_type}功能在{len(modules)}个模块中重复，建议整合为统一接口",
                        "modules": [m["module"] for m in modules]
                    })
        
        # 2. 基于命名问题的建议
        if self.analysis_results["naming_issues"]:
            recommendations.append({
                "type": "规范",
                "priority": "中",
                "description": f"发现{len(self.analysis_results['naming_issues'])}个命名问题，建议统一命名规范",
                "count": len(self.analysis_results["naming_issues"])
            })
        
        # 3. 基于模块数量的建议
        total_modules = len(self.analysis_results["module_functions"])
        if total_modules > 30:
            recommendations.append({
                "type": "架构",
                "priority": "中",
                "description": f"当前活跃模块{total_modules}个，建议按功能域进一步整合",
                "count": total_modules
            })
        
        self.analysis_results["recommendations"] = recommendations
        
        if recommendations:
            print("\n  💡 优化建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"      {i}. [{rec['priority']}] {rec['description']}")
        else:
            print("\n  ✅ 系统架构良好，无需优化")
    
    def _print_report(self):
        """打印完整报告"""
        print("\n" + "=" * 80)
        print("📊 模块功能分析报告")
        print("=" * 80)
        
        # 统计信息
        total_modules = len(self.analysis_results["module_functions"])
        total_functions = sum(
            info["function_count"] 
            for info in self.analysis_results["module_functions"].values()
        )
        duplicate_types = len(self.analysis_results["duplicate_functions"])
        naming_issues = len(self.analysis_results["naming_issues"])
        
        print(f"\n总模块数: {total_modules}")
        print(f"总方法数: {total_functions}")
        print(f"重复功能类别: {duplicate_types}")
        print(f"命名问题: {naming_issues}")
        
        # 详细信息
        print("\n" + "=" * 80)
        print("📋 模块功能详情")
        print("=" * 80)
        
        for module_key, info in self.analysis_results["module_functions"].items():
            print(f"\n{module_key} ({info['class_name']})")
            print(f"  文件: {info['file']}")
            print(f"  方法数: {info['function_count']}")
            if info['functions']:
                print(f"  主要方法: {', '.join(info['functions'][:5])}")
        
        print("\n" + "=" * 80)


def main():
    """主函数"""
    base_path = Path(__file__).parent.parent
    
    analyzer = ModuleFunctionAnalyzer(str(base_path))
    analyzer.analyze_all_modules()


if __name__ == "__main__":
    main()
