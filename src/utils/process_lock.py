"""
进程锁管理工具

提供通用的进程锁功能，防止应用程序重复启动。
可应用于 OpenClaw、Clash、交易系统等任何需要单例运行的程序。

使用方法:
    from src.utils.process_lock import ProcessLock

    lock = ProcessLock("my_app")
    if lock.acquire():
        # 运行主程序
        ...
        lock.release()
    else:
        print("另一个实例已在运行中")
"""

import os
import fcntl
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProcessLock:
    """
    进程锁管理类
    
    使用文件锁实现进程级别的单例模式，防止同一程序重复启动。
    
    特性:
    - 基于 fcntl 文件锁
    - 支持自定义锁文件路径
    - 自动清理锁文件
    - 线程安全
    
    使用示例:
        lock = ProcessLock("trading_system")
        
        if lock.acquire():
            try:
                # 运行主程序
                pass
            finally:
                lock.release()
        else:
            print("另一个实例已在运行中")
    """
    
    def __init__(self, app_name: str, lock_dir: Optional[str] = None):
        """
        初始化进程锁
        
        Args:
            app_name: 应用名称，用于生成锁文件名
            lock_dir: 锁文件目录，默认为 /tmp
        """
        self.app_name = app_name
        self.lock_dir = Path(lock_dir) if lock_dir else Path("/tmp")
        self.lock_file = self.lock_dir / f"{app_name}.lock"
        self.pid_file = self.lock_dir / f"{app_name}.pid"
        self._lock_fd: Optional[int] = None
        self._acquired = False
        
    def acquire(self) -> bool:
        """
        获取进程锁
        
        Returns:
            bool: True 表示成功获取锁，False 表示锁已被其他进程持有
        """
        if self._acquired:
            return True
        
        try:
            self._lock_fd = os.open(
                str(self.lock_file), 
                os.O_WRONLY | os.O_CREAT, 
                0o644
            )
            
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            os.write(self._lock_fd, str(os.getpid()).encode())
            
            self._write_pid_file()
            
            self._acquired = True
            logger.info(f"✅ 进程锁已获取: {self.app_name} (PID: {os.getpid()})")
            return True
            
        except (IOError, OSError, BlockingIOError) as e:
            if self._lock_fd is not None:
                try:
                    os.close(self._lock_fd)
                except:
                    pass
                self._lock_fd = None
            
            existing_pid = self._read_existing_pid()
            if existing_pid:
                logger.warning(
                    f"❌ 进程锁获取失败: {self.app_name} "
                    f"(已有实例运行，PID: {existing_pid})"
                )
            else:
                logger.warning(f"❌ 进程锁获取失败: {self.app_name}")
            
            return False
    
    def release(self) -> None:
        """
        释放进程锁
        """
        if not self._acquired or self._lock_fd is None:
            return
        
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            
            try:
                os.unlink(str(self.lock_file))
            except:
                pass
            
            try:
                os.unlink(str(self.pid_file))
            except:
                pass
            
            logger.info(f"✅ 进程锁已释放: {self.app_name}")
            
        except Exception as e:
            logger.error(f"释放进程锁失败: {e}")
        finally:
            self._lock_fd = None
            self._acquired = False
    
    def is_locked(self) -> bool:
        """
        检查锁是否被持有
        
        Returns:
            bool: True 表示锁已被持有（可能由当前进程或其他进程）
        """
        if self._acquired:
            return True
        
        try:
            fd = os.open(str(self.lock_file), os.O_WRONLY | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                return False
            except BlockingIOError:
                os.close(fd)
                return True
        except:
            return False
    
    def get_lock_info(self) -> Optional[dict]:
        """
        获取锁信息
        
        Returns:
            dict: 包含锁信息的字典，或 None
        """
        info = {
            "app_name": self.app_name,
            "lock_file": str(self.lock_file),
            "pid_file": str(self.pid_file),
            "acquired": self._acquired,
            "current_pid": os.getpid() if self._acquired else None,
            "existing_pid": self._read_existing_pid() if not self._acquired else None
        }
        return info
    
    def _write_pid_file(self) -> None:
        """写入 PID 文件"""
        try:
            with open(str(self.pid_file), 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.warning(f"写入 PID 文件失败: {e}")
    
    def _read_existing_pid(self) -> Optional[int]:
        """读取已存在的 PID"""
        try:
            if self.pid_file.exists():
                with open(str(self.pid_file), 'r') as f:
                    return int(f.read().strip())
        except:
            pass
        return None
    
    def __enter__(self):
        """支持 with 语句"""
        if self.acquire():
            return self
        raise RuntimeError(f"无法获取进程锁: {self.app_name}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.release()
        return False
    
    def __del__(self):
        """析构时自动释放锁"""
        if self._acquired:
            self.release()


def check_process_running(app_name: str) -> Optional[int]:
    """
    检查指定应用是否正在运行
    
    Args:
        app_name: 应用名称
        
    Returns:
        int: 运行中的进程 PID，或 None
    """
    lock = ProcessLock(app_name)
    if lock.is_locked():
        return lock._read_existing_pid()
    return None


def kill_process(app_name: str) -> bool:
    """
    终止指定应用的进程
    
    Args:
        app_name: 应用名称
        
    Returns:
        bool: True 表示成功终止
    """
    import signal
    
    lock = ProcessLock(app_name)
    pid = lock._read_existing_pid()
    
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"✅ 已发送终止信号给进程 {pid}")
            return True
        except ProcessLookupError:
            logger.warning(f"进程 {pid} 不存在")
            lock.release()
            return True
        except Exception as e:
            logger.error(f"终止进程失败: {e}")
            return False
    
    return False
