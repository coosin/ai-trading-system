#!/usr/bin/env python3
"""
模块重复和遗漏检查工具

全面检查系统中的所有模块，识别：
1. 功能重复的模块
2. 遗漏的核心功能
3. 不完整的模块实现
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

class ModuleAnalyzer:
    """模块分析器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.modules_dir = self.base_path / "src" / "modules"
        
        # 功能分类
        self.function_categories = {
            "记忆管理": ["memory", "mem"],
            "数据采集": ["data", "collector", "integrator"],
            "风险管理": ["risk", "safety", "security"],
            "交易执行": ["trade", "execution", "order"],
            "策略管理": ["strategy", "strat"],
            "监控告警": ["monitor", "alert", "notification"],
            "API服务": ["api", "server"],
            "LLM集成": ["llm", "language", "model"],
            "缓存管理": ["cache"],
            "日志管理": ["log"],
            "配置管理": ["config"],
            "数据库": ["database", "db"],
            "事件系统": ["event"],
            "插件系统": ["plugin"],
            "回测系统": ["backtest"],
        }
        
        # 分析结果
        self.duplicate_modules = defaultdict(list)
        self.missing_features = []
        self.incomplete_modules = []
        self.all_modules = []
    
    def scan_all_modules(self):
        """扫描所有模块"""
        print("=" * 80)
        print("🔍 扫描所有模块文件...")
        print("=" * 80)
        
        # 扫描所有Python文件
        for py_file in self.modules_dir.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            
            # 读取文件内容
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 提取类名
                classes = re.findall(r'class\s+(\w+(?:Manager|System|Engine|Monitor|Controller))', content)
                
                # 提取功能关键词
                file_path_str = str(py_file.relative_to(self.base_path))
                module_info = {
                    "file": file_path_str,
                    "classes": classes,
                    "size": len(content),
                    "has_initialize": "async def initialize" in content or "def initialize" in content,
                    "has_start": "async def start" in content or "def start" in content,
                    "has_stop": "async def stop" in content or "def stop" in content,
                    "has_cleanup": "async def cleanup" in content or "def cleanup" in content,
                }
                
                self.all_modules.append(module_info)
                
            except Exception as e:
                print(f"⚠️ 读取文件失败 {py_file}: {e}")
        
        print(f"✅ 扫描完成，共找到 {len(self.all_modules)} 个模块文件")
        return self.all_modules
    
    def find_duplicates(self):
        """查找重复功能的模块"""
        print("\n" + "=" * 80)
        print("🔍 检查功能重复的模块...")
        print("=" * 80)
        
        # 按功能分类
        for category, keywords in self.function_categories.items():
            matched_modules = []
            
            for module in self.all_modules:
                file_lower = module["file"].lower()
                
                # 检查文件名或类名是否包含关键词
                if any(kw in file_lower for kw in keywords):
                    matched_modules.append(module)
                elif any(any(kw in cls.lower() for kw in keywords) for cls in module["classes"]):
                    matched_modules.append(module)
            
            if len(matched_modules) > 1:
                self.duplicate_modules[category] = matched_modules
        
        # 打印重复模块
        for category, modules in self.duplicate_modules.items():
            print(f"\n📋 {category} ({len(modules)}个模块):")
            for module in modules:
                print(f"   - {module['file']}")
                if module['classes']:
                    print(f"     类: {', '.join(module['classes'])}")
        
        return self.duplicate_modules
    
    def check_incomplete_modules(self):
        """检查不完整的模块"""
        print("\n" + "=" * 80)
        print("🔍 检查不完整的模块...")
        print("=" * 80)
        
        for module in self.all_modules:
            issues = []
            
            # 检查是否有类定义
            if not module['classes']:
                continue  # 跳过工具文件
            
            # 检查生命周期方法
            if not module['has_initialize']:
                issues.append("缺少initialize方法")
            
            if not module['has_cleanup']:
                issues.append("缺少cleanup方法")
            
            # 检查文件大小（太小可能不完整）
            if module['size'] < 500:
                issues.append(f"文件过小 ({module['size']} bytes)")
            
            if issues:
                self.incomplete_modules.append({
                    "module": module,
                    "issues": issues
                })
        
        # 打印不完整模块
        if self.incomplete_modules:
            print(f"\n⚠️ 发现 {len(self.incomplete_modules)} 个不完整的模块:")
            for item in self.incomplete_modules:
                print(f"\n   {item['module']['file']}")
                for issue in item['issues']:
                    print(f"      - {issue}")
        else:
            print("\n✅ 所有模块都完整")
        
        return self.incomplete_modules
    
    def check_missing_features(self):
        """检查遗漏的核心功能"""
        print("\n" + "=" * 80)
        print("🔍 检查遗漏的核心功能...")
        print("=" * 80)
        
        # 定义必需的核心功能
        required_features = {
            "核心系统": [
                "config_manager",
                "database_manager",
                "cache_manager",
                "log_manager",
                "event_system",
            ],
            "AI决策": [
                "llm_integration",
                "ai_trading_engine",
                "ai_core_decision_engine",
            ],
            "记忆系统": [
                "unified_memory_system",
            ],
            "数据采集": [
                "unified_info_collector",
            ],
            "交易执行": [
                "trade_engine",
                "trading_execution_engine",
            ],
            "风险管理": [
                "risk_manager",
                "account_risk_monitor",
            ],
            "监控告警": [
                "trading_monitor",
                "intelligent_monitoring",
            ],
            "通知系统": [
                "telegram_bot",
                "notification_manager",
            ],
            "安全系统": [
                "security_manager",
                "api_key_manager",
                "emergency_stop",
            ],
            "API服务": [
                "api_server",
            ],
        }
        
        # 检查每个必需功能
        for category, features in required_features.items():
            for feature in features:
                found = False
                for module in self.all_modules:
                    if feature in module['file'].lower():
                        found = True
                        break
                
                if not found:
                    self.missing_features.append({
                        "category": category,
                        "feature": feature
                    })
        
        # 打印遗漏功能
        if self.missing_features:
            print(f"\n⚠️ 发现 {len(self.missing_features)} 个遗漏的核心功能:")
            for item in self.missing_features:
                print(f"   [{item['category']}] {item['feature']}")
        else:
            print("\n✅ 所有核心功能都已实现")
        
        return self.missing_features
    
    def generate_report(self):
        """生成完整报告"""
        print("\n" + "=" * 80)
        print("📊 模块分析报告")
        print("=" * 80)
        
        print(f"\n总模块数: {len(self.all_modules)}")
        print(f"功能重复类别: {len(self.duplicate_modules)}")
        print(f"不完整模块: {len(self.incomplete_modules)}")
        print(f"遗漏功能: {len(self.missing_features)}")
        
        # 重复模块统计
        if self.duplicate_modules:
            print("\n" + "=" * 80)
            print("🔴 功能重复统计")
            print("=" * 80)
            for category, modules in sorted(self.duplicate_modules.items(), key=lambda x: len(x[1]), reverse=True):
                print(f"\n{category}: {len(modules)}个模块")
                for module in modules:
                    print(f"   - {Path(module['file']).name}")
        
        # 建议
        print("\n" + "=" * 80)
        print("💡 优化建议")
        print("=" * 80)
        
        if self.duplicate_modules:
            print("\n1. 整合重复模块:")
            for category, modules in self.duplicate_modules.items():
                if len(modules) > 2:
                    print(f"   - {category}: 建议整合为1-2个核心模块")
        
        if self.incomplete_modules:
            print("\n2. 完善不完整模块:")
            print(f"   - 共{len(self.incomplete_modules)}个模块需要完善")
        
        if self.missing_features:
            print("\n3. 补充遗漏功能:")
            for item in self.missing_features:
                print(f"   - [{item['category']}] {item['feature']}")
        
        print("\n" + "=" * 80)


def main():
    """主函数"""
    base_path = Path(__file__).parent.parent
    
    analyzer = ModuleAnalyzer(str(base_path))
    
    # 执行分析
    analyzer.scan_all_modules()
    analyzer.find_duplicates()
    analyzer.check_incomplete_modules()
    analyzer.check_missing_features()
    
    # 生成报告
    analyzer.generate_report()


if __name__ == "__main__":
    main()
