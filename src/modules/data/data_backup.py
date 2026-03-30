import os
import json
import logging
import shutil
import zipfile
import tarfile
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class DataBackupManager:
    """数据备份管理器"""
    
    def __init__(self, base_path: str = "./data", backup_path: str = "./backups"):
        """
        初始化数据备份管理器
        
        Args:
            base_path: 数据存储基础路径
            backup_path: 备份存储路径
        """
        self.base_path = base_path
        self.backup_path = backup_path
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 创建备份目录
        os.makedirs(self.backup_path, exist_ok=True)
        
        # 备份配置
        self.backup_config = {
            'schedule': 'daily',  # daily, weekly, monthly
            'retention_days': 30,
            'compression': 'zip',  # zip, tar
            'remote_backup': False,
            'remote_config': {}
        }
    
    async def configure_backup(self, config: Dict[str, Any]):
        """
        配置备份设置
        
        Args:
            config: 备份配置
        """
        self.backup_config.update(config)
        logger.info(f"备份配置已更新: {self.backup_config}")
    
    async def create_backup(self, backup_name: Optional[str] = None, 
                          include_data: bool = True, 
                          include_config: bool = True, 
                          include_logs: bool = False) -> str:
        """
        创建数据备份
        
        Args:
            backup_name: 备份名称
            include_data: 是否包含数据
            include_config: 是否包含配置
            include_logs: 是否包含日志
            
        Returns:
            备份文件路径
        """
        try:
            # 生成备份名称
            if not backup_name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_name = f"backup_{timestamp}"
            
            # 创建备份文件路径
            backup_file = os.path.join(self.backup_path, f"{backup_name}.{self.backup_config['compression']}")
            
            # 准备要备份的文件和目录
            items_to_backup = []
            
            if include_data:
                data_dir = os.path.join(self.base_path, "market_data")
                if os.path.exists(data_dir):
                    items_to_backup.append((data_dir, "market_data"))
            
            if include_config:
                config_dir = os.path.join(self.base_path, "config")
                if os.path.exists(config_dir):
                    items_to_backup.append((config_dir, "config"))
            
            if include_logs:
                logs_dir = os.path.join(self.base_path, "logs")
                if os.path.exists(logs_dir):
                    items_to_backup.append((logs_dir, "logs"))
            
            if not items_to_backup:
                logger.warning("没有要备份的内容")
                return ""
            
            # 创建压缩文件
            if self.backup_config['compression'] == 'zip':
                await self._create_zip_backup(backup_file, items_to_backup)
            else:
                await self._create_tar_backup(backup_file, items_to_backup)
            
            # 清理过期备份
            await self._cleanup_old_backups()
            
            # 执行远程备份（如果配置）
            if self.backup_config.get('remote_backup', False):
                await self._backup_to_remote(backup_file)
            
            logger.info(f"备份创建成功: {backup_file}")
            return backup_file
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            return ""
    
    async def restore_backup(self, backup_file: str, 
                           restore_data: bool = True, 
                           restore_config: bool = True, 
                           restore_logs: bool = False) -> bool:
        """
        恢复数据备份
        
        Args:
            backup_file: 备份文件路径
            restore_data: 是否恢复数据
            restore_config: 是否恢复配置
            restore_logs: 是否恢复日志
            
        Returns:
            是否恢复成功
        """
        try:
            if not os.path.exists(backup_file):
                logger.error(f"备份文件不存在: {backup_file}")
                return False
            
            # 临时解压目录
            temp_dir = os.path.join(self.backup_path, f"temp_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 解压备份文件
            if backup_file.endswith('.zip'):
                await self._extract_zip_backup(backup_file, temp_dir)
            elif backup_file.endswith('.tar') or backup_file.endswith('.tar.gz'):
                await self._extract_tar_backup(backup_file, temp_dir)
            else:
                logger.error(f"不支持的备份文件格式: {backup_file}")
                shutil.rmtree(temp_dir)
                return False
            
            # 恢复数据
            if restore_data:
                data_source = os.path.join(temp_dir, "market_data")
                data_dest = os.path.join(self.base_path, "market_data")
                if os.path.exists(data_source):
                    # 备份当前数据
                    if os.path.exists(data_dest):
                        backup_current = os.path.join(self.base_path, f"market_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        shutil.move(data_dest, backup_current)
                    # 恢复数据
                    shutil.copytree(data_source, data_dest)
                    logger.info("数据恢复成功")
            
            # 恢复配置
            if restore_config:
                config_source = os.path.join(temp_dir, "config")
                config_dest = os.path.join(self.base_path, "config")
                if os.path.exists(config_source):
                    # 备份当前配置
                    if os.path.exists(config_dest):
                        backup_current = os.path.join(self.base_path, f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        shutil.move(config_dest, backup_current)
                    # 恢复配置
                    shutil.copytree(config_source, config_dest)
                    logger.info("配置恢复成功")
            
            # 恢复日志
            if restore_logs:
                logs_source = os.path.join(temp_dir, "logs")
                logs_dest = os.path.join(self.base_path, "logs")
                if os.path.exists(logs_source):
                    # 备份当前日志
                    if os.path.exists(logs_dest):
                        backup_current = os.path.join(self.base_path, f"logs_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                        shutil.move(logs_dest, backup_current)
                    # 恢复日志
                    shutil.copytree(logs_source, logs_dest)
                    logger.info("日志恢复成功")
            
            # 清理临时目录
            shutil.rmtree(temp_dir)
            
            logger.info(f"备份恢复成功: {backup_file}")
            return True
        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            return False
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """
        列出所有备份
        
        Returns:
            备份列表
        """
        try:
            backups = []
            if not os.path.exists(self.backup_path):
                return backups
            
            for file_name in os.listdir(self.backup_path):
                if file_name.endswith(('.zip', '.tar', '.tar.gz')):
                    file_path = os.path.join(self.backup_path, file_name)
                    file_stat = os.stat(file_path)
                    backups.append({
                        'name': file_name,
                        'path': file_path,
                        'size': file_stat.st_size,
                        'created_at': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        'type': file_name.split('.')[-1]
                    })
            
            # 按创建时间排序
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            return backups
        except Exception as e:
            logger.error(f"列出备份失败: {e}")
            return []
    
    async def delete_backup(self, backup_file: str) -> bool:
        """
        删除备份
        
        Args:
            backup_file: 备份文件路径
            
        Returns:
            是否删除成功
        """
        try:
            if os.path.exists(backup_file):
                os.remove(backup_file)
                logger.info(f"备份删除成功: {backup_file}")
                return True
            else:
                logger.error(f"备份文件不存在: {backup_file}")
                return False
        except Exception as e:
            logger.error(f"删除备份失败: {e}")
            return False
    
    async def schedule_backup(self):
        """
        定时执行备份
        """
        while True:
            try:
                # 检查是否需要执行备份
                if await self._should_run_backup():
                    await self.create_backup()
            except Exception as e:
                logger.error(f"定时备份失败: {e}")
            
            # 根据备份计划设置等待时间
            await asyncio.sleep(self._get_schedule_interval())
    
    async def _create_zip_backup(self, backup_file: str, items: List[Tuple[str, str]]):
        """
        创建ZIP格式备份
        """
        def _sync_create_zip():
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for src_path, arcname in items:
                    if os.path.isdir(src_path):
                        for root, _, files in os.walk(src_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_path = os.path.join(arcname, os.path.relpath(file_path, src_path))
                                zipf.write(file_path, arc_path)
                    else:
                        zipf.write(src_path, arcname)
        
        await asyncio.get_event_loop().run_in_executor(self.executor, _sync_create_zip)
    
    async def _create_tar_backup(self, backup_file: str, items: List[Tuple[str, str]]):
        """
        创建TAR格式备份
        """
        def _sync_create_tar():
            mode = 'w:gz' if backup_file.endswith('.gz') else 'w'
            with tarfile.open(backup_file, mode) as tar:
                for src_path, arcname in items:
                    tar.add(src_path, arcname=arcname)
        
        await asyncio.get_event_loop().run_in_executor(self.executor, _sync_create_tar)
    
    async def _extract_zip_backup(self, backup_file: str, dest_dir: str):
        """
        解压ZIP格式备份
        """
        def _sync_extract_zip():
            with zipfile.ZipFile(backup_file, 'r') as zipf:
                zipf.extractall(dest_dir)
        
        await asyncio.get_event_loop().run_in_executor(self.executor, _sync_extract_zip)
    
    async def _extract_tar_backup(self, backup_file: str, dest_dir: str):
        """
        解压TAR格式备份
        """
        def _sync_extract_tar():
            mode = 'r:gz' if backup_file.endswith('.gz') else 'r'
            with tarfile.open(backup_file, mode) as tar:
                tar.extractall(dest_dir)
        
        await asyncio.get_event_loop().run_in_executor(self.executor, _sync_extract_tar)
    
    async def _cleanup_old_backups(self):
        """
        清理过期备份
        """
        try:
            retention_days = self.backup_config.get('retention_days', 30)
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            for backup in await self.list_backups():
                backup_date = datetime.fromisoformat(backup['created_at'])
                if backup_date < cutoff_date:
                    await self.delete_backup(backup['path'])
        except Exception as e:
            logger.error(f"清理过期备份失败: {e}")
    
    async def _backup_to_remote(self, backup_file: str):
        """
        备份到远程存储
        """
        try:
            remote_config = self.backup_config.get('remote_config', {})
            remote_type = remote_config.get('type')
            
            if remote_type == 's3':
                await self._backup_to_s3(backup_file, remote_config)
            elif remote_type == 'ftp':
                await self._backup_to_ftp(backup_file, remote_config)
            elif remote_type == 'scp':
                await self._backup_to_scp(backup_file, remote_config)
        except Exception as e:
            logger.error(f"远程备份失败: {e}")
    
    async def _backup_to_s3(self, backup_file: str, config: Dict[str, Any]):
        """
        备份到S3
        """
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError
            
            s3 = boto3.client(
                's3',
                aws_access_key_id=config.get('access_key'),
                aws_secret_access_key=config.get('secret_key'),
                region_name=config.get('region')
            )
            
            bucket_name = config.get('bucket')
            key = f"backups/{os.path.basename(backup_file)}"
            
            s3.upload_file(backup_file, bucket_name, key)
            logger.info(f"备份到S3成功: s3://{bucket_name}/{key}")
        except ImportError:
            logger.error("boto3 库未安装，无法备份到S3")
        except NoCredentialsError:
            logger.error("S3 凭证错误")
    
    async def _backup_to_ftp(self, backup_file: str, config: Dict[str, Any]):
        """
        备份到FTP
        """
        try:
            import ftplib
            
            ftp = ftplib.FTP(config.get('host'))
            ftp.login(config.get('username'), config.get('password'))
            
            # 创建备份目录
            try:
                ftp.mkd('backups')
            except:
                pass
            ftp.cwd('backups')
            
            # 上传文件
            with open(backup_file, 'rb') as f:
                ftp.storbinary(f'STOR {os.path.basename(backup_file)}', f)
            
            ftp.quit()
            logger.info(f"备份到FTP成功: {config.get('host')}")
        except ImportError:
            logger.error("ftplib 库未安装，无法备份到FTP")
    
    async def _backup_to_scp(self, backup_file: str, config: Dict[str, Any]):
        """
        备份到SCP
        """
        try:
            import paramiko
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                config.get('host'),
                username=config.get('username'),
                password=config.get('password'),
                key_filename=config.get('key_file')
            )
            
            sftp = ssh.open_sftp()
            
            # 创建备份目录
            try:
                sftp.mkdir('backups')
            except:
                pass
            
            # 上传文件
            remote_path = f"backups/{os.path.basename(backup_file)}"
            sftp.put(backup_file, remote_path)
            
            sftp.close()
            ssh.close()
            logger.info(f"备份到SCP成功: {config.get('host')}")
        except ImportError:
            logger.error("paramiko 库未安装，无法备份到SCP")
    
    async def _should_run_backup(self) -> bool:
        """
        检查是否应该执行备份
        """
        # 这里可以实现更复杂的备份计划逻辑
        # 简单实现：每天执行一次
        last_backup = await self._get_last_backup_time()
        if not last_backup:
            return True
        
        days_since_last = (datetime.now() - last_backup).days
        if self.backup_config.get('schedule') == 'daily' and days_since_last >= 1:
            return True
        elif self.backup_config.get('schedule') == 'weekly' and days_since_last >= 7:
            return True
        elif self.backup_config.get('schedule') == 'monthly' and days_since_last >= 30:
            return True
        
        return False
    
    async def _get_last_backup_time(self) -> Optional[datetime]:
        """
        获取最后一次备份时间
        """
        backups = await self.list_backups()
        if not backups:
            return None
        
        last_backup = backups[0]
        return datetime.fromisoformat(last_backup['created_at'])
    
    def _get_schedule_interval(self) -> int:
        """
        获取计划间隔（秒）
        """
        schedule = self.backup_config.get('schedule', 'daily')
        if schedule == 'daily':
            return 24 * 60 * 60  # 24小时
        elif schedule == 'weekly':
            return 7 * 24 * 60 * 60  # 7天
        elif schedule == 'monthly':
            return 30 * 24 * 60 * 60  # 30天
        else:
            return 24 * 60 * 60  # 默认24小时
    
    def close(self):
        """
        关闭资源
        """
        self.executor.shutdown()
        logger.info("数据备份管理器已关闭")

# 使用示例
if __name__ == "__main__":
    async def main():
        # 创建备份管理器
        backup_manager = DataBackupManager()
        
        # 配置备份
        await backup_manager.configure_backup({
            'schedule': 'daily',
            'retention_days': 7,
            'compression': 'zip'
        })
        
        # 创建备份
        backup_file = await backup_manager.create_backup()
        print(f"创建备份: {backup_file}")
        
        # 列出备份
        backups = await backup_manager.list_backups()
        print("备份列表:")
        for backup in backups:
            print(f"  - {backup['name']} ({backup['size']} bytes) - {backup['created_at']}")
        
        # 关闭资源
        backup_manager.close()
    
    asyncio.run(main())
