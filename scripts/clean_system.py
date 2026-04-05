#!/usr/bin/env python3
"""
系统清理和维护脚本

功能：
1. 清理累积的错误日志
2. 重置错误计数
3. 清理临时文件
4. 优化数据库
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SystemCleaner:
    """系统清理器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.logs_path = self.base_path / "logs"
        self.data_path = self.base_path / "data"
        
    def clean_old_logs(self, days: int = 7):
        """清理旧日志文件"""
        logger.info(f"🧹 开始清理 {days} 天前的日志文件...")
        
        if not self.logs_path.exists():
            logger.warning("日志目录不存在")
            return
        
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        cleaned_size = 0
        
        for log_file in self.logs_path.glob("*.log*"):
            try:
                # 检查文件修改时间
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff_date:
                    file_size = log_file.stat().st_size
                    log_file.unlink()
                    cleaned_count += 1
                    cleaned_size += file_size
                    logger.info(f"  删除: {log_file.name} ({file_size / 1024:.1f} KB)")
            except Exception as e:
                logger.error(f"  删除失败 {log_file.name}: {e}")
        
        logger.info(f"✅ 清理完成: {cleaned_count} 个文件, 共 {cleaned_size / 1024 / 1024:.2f} MB")
    
    def rotate_current_logs(self):
        """轮转当前日志文件"""
        logger.info("🔄 开始轮转日志文件...")
        
        if not self.logs_path.exists():
            return
        
        for log_file in self.logs_path.glob("*.log"):
            if log_file.stat().st_size > 10 * 1024 * 1024:  # 大于10MB
                try:
                    # 重命名日志文件
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_name = log_file.parent / f"{log_file.stem}_{timestamp}.log"
                    log_file.rename(new_name)
                    
                    # 创建新的空日志文件
                    log_file.touch()
                    
                    logger.info(f"  轮转: {log_file.name} -> {new_name.name}")
                except Exception as e:
                    logger.error(f"  轮转失败 {log_file.name}: {e}")
        
        logger.info("✅ 日志轮转完成")
    
    def clean_temp_files(self):
        """清理临时文件"""
        logger.info("🧹 开始清理临时文件...")
        
        temp_patterns = [
            "*.tmp",
            "*.temp",
            "*.bak",
            "*.swp",
            "*~",
            ".DS_Store",
            "Thumbs.db"
        ]
        
        cleaned_count = 0
        cleaned_size = 0
        
        for pattern in temp_patterns:
            for temp_file in self.base_path.rglob(pattern):
                try:
                    file_size = temp_file.stat().st_size
                    temp_file.unlink()
                    cleaned_count += 1
                    cleaned_size += file_size
                    logger.debug(f"  删除: {temp_file.relative_to(self.base_path)}")
                except Exception as e:
                    logger.debug(f"  删除失败: {e}")
        
        logger.info(f"✅ 清理完成: {cleaned_count} 个临时文件, 共 {cleaned_size / 1024:.1f} KB")
    
    def reset_error_counters(self):
        """重置错误计数器"""
        logger.info("🔄 重置错误计数器...")
        
        try:
            # 重置alerts.log中的错误计数
            alerts_file = self.logs_path / "alerts.log"
            if alerts_file.exists():
                with open(alerts_file, 'w') as f:
                    f.write(f"# Error counters reset at {datetime.now().isoformat()}\n")
                logger.info("  ✅ 重置 alerts.log")
            
            logger.info("✅ 错误计数器已重置")
        except Exception as e:
            logger.error(f"  重置失败: {e}")
    
    def clean_old_backups(self, keep_count: int = 5):
        """清理旧备份文件"""
        logger.info(f"🧹 清理旧备份文件，保留最近 {keep_count} 个...")
        
        backup_path = self.base_path / "backups"
        if not backup_path.exists():
            return
        
        # 获取所有备份文件并按时间排序
        backups = sorted(
            backup_path.glob("backup_*.tar.gz"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        # 删除旧备份
        for backup in backups[keep_count:]:
            try:
                file_size = backup.stat().st_size
                backup.unlink()
                logger.info(f"  删除: {backup.name} ({file_size / 1024 / 1024:.2f} MB)")
            except Exception as e:
                logger.error(f"  删除失败 {backup.name}: {e}")
        
        logger.info(f"✅ 备份清理完成，保留 {min(len(backups), keep_count)} 个")
    
    def run_all(self):
        """运行所有清理任务"""
        logger.info("=" * 60)
        logger.info("🚀 开始系统清理和维护")
        logger.info("=" * 60)
        
        self.clean_old_logs(days=7)
        self.rotate_current_logs()
        self.clean_temp_files()
        self.reset_error_counters()
        self.clean_old_backups(keep_count=5)
        
        logger.info("=" * 60)
        logger.info("✅ 系统清理和维护完成")
        logger.info("=" * 60)


def main():
    """主函数"""
    base_path = Path(__file__).parent.parent
    cleaner = SystemCleaner(base_path)
    cleaner.run_all()


if __name__ == "__main__":
    main()
