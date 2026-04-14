#!/usr/bin/env python3
"""
语法检查工具 - 帮助AI提升代码质量
"""

import subprocess
import sys
import os
import glob

def check_python_file(filepath):
    """检查单个Python文件的语法"""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile', filepath],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✅ {filepath} - 语法正确")
            return True
        else:
            print(f"❌ {filepath} - 语法错误:")
            print(f"   {result.stderr}")
            return False
            
    except Exception as e:
        print(f"⚠️ {filepath} - 检查失败: {e}")
        return False

def check_all_python_files(directory):
    """检查目录下所有Python文件"""
    print(f"🔍 开始检查目录: {directory}")
    print("=" * 60)
    
    python_files = glob.glob(f"{directory}/**/*.py", recursive=True)
    
    total_files = len(python_files)
    passed_files = 0
    failed_files = 0
    
    for filepath in python_files:
        relative_path = os.path.relpath(filepath, directory)
        if check_python_file(filepath):
            passed_files += 1
        else:
            failed_files += 1
    
    print("=" * 60)
    print(f"📊 检查结果:")
    print(f"   总计文件: {total_files}")
    print(f"   通过: {passed_files}")
    print(f"   失败: {failed_files}")
    
    return failed_files == 0

def check_modified_files():
    """检查我们修改过的文件"""
    modified_files = [
        "/home/cool/.openclaw-trading/src/modules/intelligence/natural_language_interface.py",
        "/home/cool/.openclaw-trading/src/modules/core/emotional_intelligence.py",
        "/home/cool/.openclaw-trading/src/modules/core/personality_config.py",
        "/home/cool/.openclaw-trading/src/modules/core/proactive_care.py"
    ]
    
    print("🔍 检查优化修改的文件:")
    print("=" * 60)
    
    all_passed = True
    for filepath in modified_files:
        if os.path.exists(filepath):
            if not check_python_file(filepath):
                all_passed = False
        else:
            print(f"⚠️ {filepath} - 文件不存在")
    
    return all_passed

def main():
    """主函数"""
    print("🎯 AI代码语法检查工具")
    print("帮助提升代码质量，避免语法错误")
    print("=" * 60)
    
    # 1. 检查整个项目
    print("\n1. 检查整个项目语法...")
    project_root = "/home/cool/.openclaw-trading"
    check_all_python_files(project_root)
    
    # 2. 检查我们修改的文件
    print("\n2. 检查优化修改的文件...")
    if not check_modified_files():
        print("\n❌ 发现语法错误，请修复后再继续")
        return False
    
    # 3. 检查关键模块
    print("\n3. 检查关键模块...")
    key_modules = [
        "/home/cool/.openclaw-trading/src/modules/core",
        "/home/cool/.openclaw-trading/src/modules/intelligence"
    ]
    
    for module in key_modules:
        if os.path.exists(module):
            check_all_python_files(module)
    
    print("\n✅ 语法检查完成")
    print("🎯 建议: 每次修改后都运行此工具检查语法")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)