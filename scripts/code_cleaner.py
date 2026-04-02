#!/usr/bin/env python3
"""
代码清理脚本 - 批量修复print语句和异常处理
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

class CodeCleaner:
    """代码清理器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.src_dir = self.project_root / "src"
        self.fixed_files = []
        self.errors = []
    
    def clean_all(self):
        """执行所有清理任务"""
        print("🧹 开始代码清理...")
        
        # 1. 清理print语句
        print("\n📝 清理print语句...")
        self._clean_print_statements()
        
        # 2. 清理空文件
        print("\n🗑️ 清理空文件...")
        self._clean_empty_files()
        
        # 3. 清理重复文件
        print("\n🔍 识别重复文件...")
        self._identify_duplicate_files()
        
        # 4. 生成报告
        self._generate_report()
    
    def _clean_print_statements(self):
        """清理所有print语句"""
        python_files = list(self.src_dir.rglob("*.py"))
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # 替换print语句为logger
                content = self._replace_print_with_logger(content)
                
                if content != original_content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.fixed_files.append(str(file_path))
                    print(f"  ✅ 修复: {file_path.relative_to(self.project_root)}")
            
            except Exception as e:
                self.errors.append(f"{file_path}: {e}")
                print(f"  ❌ 错误: {file_path.relative_to(self.project_root)} - {e}")
    
    def _replace_print_with_logger(self, content: str) -> str:
        """将print语句替换为logger调用"""
        
        # 模式1: print(f"[DEBUG] ...") -> logger.debug(...)
        content = re.sub(
            r'print\(f"\[DEBUG\]\s*([^"]+)"\)',
            r'logger.debug(f"\1")',
            content
        )
        
        # 模式2: print(f"[ERROR] ...") -> logger.error(...)
        content = re.sub(
            r'print\(f"\[ERROR\]\s*([^"]+)"\)',
            r'logger.error(f"\1")',
            content
        )
        
        # 模式3: print(f"[INFO] ...") -> logger.info(...)
        content = re.sub(
            r'print\(f"\[INFO\]\s*([^"]+)"\)',
            r'logger.info(f"\1")',
            content
        )
        
        # 模式4: print(f"[WARNING] ...") -> logger.warning(...)
        content = re.sub(
            r'print\(f"\[WARNING\]\s*([^"]+)"\)',
            r'logger.warning(f"\1")',
            content
        )
        
        # 模式5: print("...") -> logger.info("...")
        content = re.sub(
            r'print\("([^"]+)"\)',
            r'logger.info("\1")',
            content
        )
        
        # 模式6: print(f"...") -> logger.info(f"...")
        content = re.sub(
            r'print\(f"([^"]+)"\)',
            r'logger.info(f"\1")',
            content
        )
        
        # 模式7: print(...) -> logger.info(...)
        content = re.sub(
            r'print\(([^)]+)\)',
            r'logger.info(\1)',
            content
        )
        
        return content
    
    def _clean_empty_files(self):
        """清理空文件"""
        empty_files = []
        
        for file_path in self.src_dir.rglob("*.py"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                # 检查是否为空文件或只有注释
                if not content or content.startswith('#') and '\n' not in content:
                    empty_files.append(file_path)
            
            except Exception as e:
                print(f"  ⚠️ 无法读取: {file_path} - {e}")
        
        if empty_files:
            print(f"\n  发现 {len(empty_files)} 个空文件:")
            for file_path in empty_files:
                print(f"    - {file_path.relative_to(self.project_root)}")
        else:
            print("  ✅ 未发现空文件")
    
    def _identify_duplicate_files(self):
        """识别重复文件"""
        # 识别功能相似的文件
        duplicates = {
            "trading_engine": [
                "src/modules/core/ai_trading_engine.py",
                "src/modules/core/trade_engine.py"
            ],
            "memory_manager": [
                "src/modules/core/ai_memory.py",
                "src/modules/core/memory_manager.py",
                "src/modules/core/enhanced_memory_manager.py"
            ],
            "risk_manager": [
                "src/modules/core/risk_manager.py",
                "src/modules/core/account_risk_monitor.py"
            ]
        }
        
        print("\n  发现可能的重复模块:")
        for name, files in duplicates.items():
            existing_files = [f for f in files if (self.project_root / f).exists()]
            if len(existing_files) > 1:
                print(f"\n  📦 {name}:")
                for file_path in existing_files:
                    print(f"    - {file_path}")
    
    def _generate_report(self):
        """生成清理报告"""
        print("\n" + "="*60)
        print("📊 清理报告")
        print("="*60)
        print(f"✅ 修复的文件数: {len(self.fixed_files)}")
        print(f"❌ 错误数: {len(self.errors)}")
        
        if self.fixed_files:
            print("\n修复的文件:")
            for file_path in self.fixed_files[:10]:  # 只显示前10个
                print(f"  - {file_path}")
            if len(self.fixed_files) > 10:
                print(f"  ... 还有 {len(self.fixed_files) - 10} 个文件")
        
        if self.errors:
            print("\n错误:")
            for error in self.errors:
                print(f"  - {error}")
        
        print("\n✅ 清理完成!")


if __name__ == "__main__":
    cleaner = CodeCleaner("/home/cool/.openclaw-trading")
    cleaner.clean_all()
