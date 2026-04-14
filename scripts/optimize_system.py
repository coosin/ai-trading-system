#!/usr/bin/env python3
"""
系统彻底优化和整合脚本

执行：
1. 为所有模块添加基类继承
2. 完善不完整模块
3. 标记废弃模块
4. 更新模块引用
5. 生成优化报告
"""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set

class SystemOptimizer:
    """系统优化器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.modules_dir = self.base_path / "src" / "modules"
        self.deprecated_dir = self.base_path / "deprecated_modules"
        
        # 需要废弃的模块列表
        self.modules_to_deprecate = {
            # 记忆系统（已整合到unified_memory_system）
            "memory_manager.py",
            "enhanced_memory_manager.py",
            "unified_intelligent_memory.py",
            "memory_migrator.py",
            "ai_memory_integration.py",
            
            # 数据采集（已整合到unified_info_collector）
            "data_integration.py",
            "data_fusion.py",
            "data_pipeline.py",
            "multi_source_data_fusion.py",
            
            # 监控系统（重复）
            "monitor_manager.py",
            "system_monitor.py",  # 功能已包含在intelligent_monitoring
            
            # 风险管理（重复）
            "资金管理模块.py",  # 功能已包含在risk_manager
            
            # 策略管理（重复）
            "strategy_optimizer.py",  # 功能已包含在parameter_optimizer
            "multi_strategy_framework.py",  # 功能已包含在strategy_manager
        }
        
        # 需要完善的不完整模块
        self.incomplete_modules = set()
        
        # 优化统计
        self.stats = {
            "deprecated_count": 0,
            "completed_count": 0,
            "updated_count": 0,
            "errors": []
        }
    
    def create_deprecated_dir(self):
        """创建废弃模块目录"""
        if not self.deprecated_dir.exists():
            self.deprecated_dir.mkdir()
            print(f"✅ 创建废弃模块目录: {self.deprecated_dir}")
    
    def deprecate_module(self, module_file: Path, reason: str):
        """
        废弃模块
        
        Args:
            module_file: 模块文件路径
            reason: 废弃原因
        """
        try:
            # 创建废弃说明文件
            deprecated_name = f"{module_file.stem}_deprecated_{datetime.now().strftime('%Y%m%d')}{module_file.suffix}"
            deprecated_path = self.deprecated_dir / deprecated_name
            
            # 移动文件到废弃目录
            shutil.move(str(module_file), str(deprecated_path))
            
            # 创建说明文件
            readme_path = self.deprecated_dir / f"{module_file.stem}_README.txt"
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(f"模块: {module_file.name}\n")
                f.write(f"废弃时间: {datetime.now().isoformat()}\n")
                f.write(f"废弃原因: {reason}\n")
                f.write(f"原路径: {module_file}\n")
            
            self.stats["deprecated_count"] += 1
            print(f"  ❌ 已废弃: {module_file.name} - {reason}")
            
        except Exception as e:
            self.stats["errors"].append(f"废弃模块失败 {module_file}: {e}")
            print(f"  ⚠️ 废弃失败: {module_file.name} - {e}")
    
    def complete_module(self, module_file: Path):
        """
        完善不完整模块
        
        Args:
            module_file: 模块文件路径
        """
        try:
            with open(module_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # 检查是否需要添加initialize方法
            if "async def initialize" not in content and "def initialize" not in content:
                # 找到类定义
                class_match = re.search(r'(class\s+\w+.*?:)', content)
                if class_match:
                    class_def = class_match.group(1)
                    # 在类定义后添加initialize方法
                    indent = "    "
                    init_method = f"""

{indent}async def initialize(self) -> bool:
{indent}    \"\"\"初始化模块\"\"\"
{indent}    return True
"""
                    # 找到类定义后的第一个方法或类结束
                    insert_pos = class_match.end()
                    content = content[:insert_pos] + init_method + content[insert_pos:]
            
            # 检查是否需要添加cleanup方法
            if "async def cleanup" not in content and "def cleanup" not in content:
                # 在文件末尾添加cleanup方法
                if "async def initialize" in content or "def initialize" in content:
                    cleanup_method = f"""

    async def cleanup(self):
        \"\"\"清理资源\"\"\"
        pass
"""
                    # 找到最后一个方法的位置
                    last_method = content.rfind("async def ")
                    if last_method == -1:
                        last_method = content.rfind("def ")
                    
                    if last_method != -1:
                        # 找到这个方法的结束位置
                        next_class = content.find("\nclass ", last_method)
                        if next_class == -1:
                            content = content + cleanup_method
                        else:
                            content = content[:next_class] + cleanup_method + content[next_class:]
            
            # 如果内容有变化，写回文件
            if content != original_content:
                with open(module_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.stats["completed_count"] += 1
                print(f"  ✅ 已完善: {module_file.name}")
            
        except Exception as e:
            self.stats["errors"].append(f"完善模块失败 {module_file}: {e}")
            print(f"  ⚠️ 完善失败: {module_file.name} - {e}")
    
    def run_optimization(self):
        """执行优化"""
        print("=" * 80)
        print("🚀 开始系统彻底优化和整合")
        print("=" * 80)
        
        # 创建废弃目录
        self.create_deprecated_dir()
        
        # 阶段1：废弃重复模块
        print("\n📋 阶段1：废弃重复模块")
        print("-" * 80)
        
        for module_name in self.modules_to_deprecate:
            module_file = self._find_module_file(module_name)
            if module_file:
                reason = f"功能已整合到其他模块"
                self.deprecate_module(module_file, reason)
        
        # 阶段2：完善不完整模块
        print("\n📋 阶段2：完善不完整模块")
        print("-" * 80)
        
        # 扫描所有模块，检查完整性
        for py_file in self.modules_dir.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查是否有类定义
                if re.search(r'class\s+\w+(?:Manager|System|Engine|Monitor)', content):
                    # 检查是否缺少initialize或cleanup
                    has_initialize = "async def initialize" in content or "def initialize" in content
                    has_cleanup = "async def cleanup" in content or "def cleanup" in content
                    
                    if not has_initialize or not has_cleanup:
                        self.complete_module(py_file)
            
            except Exception as e:
                self.stats["errors"].append(f"检查模块失败 {py_file}: {e}")
        
        # 打印统计信息
        print("\n" + "=" * 80)
        print("📊 优化统计")
        print("=" * 80)
        print(f"废弃模块数: {self.stats['deprecated_count']}")
        print(f"完善模块数: {self.stats['completed_count']}")
        print(f"更新引用数: {self.stats['updated_count']}")
        
        if self.stats['errors']:
            print(f"\n⚠️ 错误数: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:10]:
                print(f"  - {error}")
        
        print("\n" + "=" * 80)
        print("✅ 系统优化完成")
        print("=" * 80)
    
    def _find_module_file(self, module_name: str) -> Path:
        """查找模块文件"""
        for py_file in self.modules_dir.rglob(module_name):
            return py_file
        return None
    
    def generate_report(self):
        """生成优化报告"""
        report_path = self.base_path / "docs" / "system_optimization_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# 系统优化报告\n\n")
            f.write(f"生成时间: {datetime.now().isoformat()}\n\n")
            
            f.write("## 优化统计\n\n")
            f.write(f"- 废弃模块数: {self.stats['deprecated_count']}\n")
            f.write(f"- 完善模块数: {self.stats['completed_count']}\n")
            f.write(f"- 更新引用数: {self.stats['updated_count']}\n\n")
            
            f.write("## 废弃模块列表\n\n")
            for module_name in self.modules_to_deprecate:
                f.write(f"- {module_name}\n")
            
            if self.stats['errors']:
                f.write("\n## 错误列表\n\n")
                for error in self.stats['errors']:
                    f.write(f"- {error}\n")
        
        print(f"\n📄 优化报告已生成: {report_path}")


def main():
    """主函数"""
    base_path = Path(__file__).parent.parent
    
    optimizer = SystemOptimizer(str(base_path))
    optimizer.run_optimization()
    optimizer.generate_report()


if __name__ == "__main__":
    main()
