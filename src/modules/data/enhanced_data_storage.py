import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

# 可选导入 pyarrow
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False
    pa = None
    pq = None

logger = logging.getLogger(__name__)

class EnhancedDataStorage:
    """增强的数据存储系统"""
    
    def __init__(self, base_path: str = "./data"):
        """
        初始化数据存储系统
        
        Args:
            base_path: 数据存储基础路径
        """
        self.base_path = base_path
        self.data_dir = os.path.join(base_path, "market_data")
        self.index_dir = os.path.join(base_path, "indexes")
        self.metadata_dir = os.path.join(base_path, "metadata")
        
        # 创建必要的目录
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.index_dir, exist_ok=True)
        os.makedirs(self.metadata_dir, exist_ok=True)
        
        # 初始化线程池
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def save_market_data(self, symbol: str, data: pd.DataFrame, timeframe: str = "1m") -> bool:
        """
        保存市场数据
        
        Args:
            symbol: 交易对
            data: 市场数据
            timeframe: 时间周期
            
        Returns:
            是否保存成功
        """
        try:
            # 确保数据有正确的索引
            if not isinstance(data.index, pd.DatetimeIndex):
                if 'timestamp' in data.columns:
                    data['timestamp'] = pd.to_datetime(data['timestamp'])
                    data.set_index('timestamp', inplace=True)
                else:
                    logger.error("数据缺少时间戳列")
                    return False
            
            # 排序数据
            data = data.sort_index()
            
            # 创建存储路径
            symbol_path = os.path.join(self.data_dir, symbol.replace('/', '_'))
            timeframe_path = os.path.join(symbol_path, timeframe)
            os.makedirs(timeframe_path, exist_ok=True)
            
            # 按日期分文件存储
            grouped = data.groupby(data.index.date)
            for date, group in grouped:
                date_str = date.strftime('%Y%m%d')
                file_path = os.path.join(timeframe_path, f"{date_str}.parquet")
                
                # 保存为Parquet格式
                table = pa.Table.from_pandas(group)
                pq.write_table(table, file_path, compression='snappy')
            
            # 更新元数据
            self._update_metadata(symbol, timeframe, data)
            
            # 构建索引
            self._build_index(symbol, timeframe)
            
            logger.info(f"保存市场数据成功: {symbol} {timeframe}")
            return True
        except Exception as e:
            logger.error(f"保存市场数据失败: {e}")
            return False
    
    def load_market_data(self, symbol: str, start_time: datetime, end_time: datetime, 
                        timeframe: str = "1m") -> pd.DataFrame:
        """
        加载市场数据
        
        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
            timeframe: 时间周期
            
        Returns:
            市场数据
        """
        try:
            # 创建存储路径
            symbol_path = os.path.join(self.data_dir, symbol.replace('/', '_'))
            timeframe_path = os.path.join(symbol_path, timeframe)
            
            if not os.path.exists(timeframe_path):
                return pd.DataFrame()
            
            # 获取需要加载的文件
            start_date = start_time.date()
            end_date = end_time.date()
            date_range = pd.date_range(start=start_date, end=end_date)
            
            files_to_load = []
            for date in date_range:
                date_str = date.strftime('%Y%m%d')
                file_path = os.path.join(timeframe_path, f"{date_str}.parquet")
                if os.path.exists(file_path):
                    files_to_load.append(file_path)
            
            if not files_to_load:
                return pd.DataFrame()
            
            # 并行加载文件
            def load_file(file_path):
                table = pq.read_table(file_path)
                return table.to_pandas()
            
            with ThreadPoolExecutor() as executor:
                data_frames = list(executor.map(load_file, files_to_load))
            
            # 合并数据
            data = pd.concat(data_frames)
            
            # 过滤时间范围
            data = data[(data.index >= start_time) & (data.index <= end_time)]
            
            # 排序数据
            data = data.sort_index()
            
            logger.info(f"加载市场数据成功: {symbol} {timeframe} {len(data)} 条记录")
            return data
        except Exception as e:
            logger.error(f"加载市场数据失败: {e}")
            return pd.DataFrame()
    
    def get_available_symbols(self) -> List[str]:
        """
        获取可用的交易对
        
        Returns:
            交易对列表
        """
        try:
            symbols = []
            if os.path.exists(self.data_dir):
                for item in os.listdir(self.data_dir):
                    item_path = os.path.join(self.data_dir, item)
                    if os.path.isdir(item_path):
                        # 恢复原始交易对格式
                        symbol = item.replace('_', '/')
                        symbols.append(symbol)
            return symbols
        except Exception as e:
            logger.error(f"获取可用交易对失败: {e}")
            return []
    
    def get_available_timeframes(self, symbol: str) -> List[str]:
        """
        获取可用的时间周期
        
        Args:
            symbol: 交易对
            
        Returns:
            时间周期列表
        """
        try:
            timeframes = []
            symbol_path = os.path.join(self.data_dir, symbol.replace('/', '_'))
            if os.path.exists(symbol_path):
                for item in os.listdir(symbol_path):
                    item_path = os.path.join(symbol_path, item)
                    if os.path.isdir(item_path):
                        timeframes.append(item)
            return timeframes
        except Exception as e:
            logger.error(f"获取可用时间周期失败: {e}")
            return []
    
    def get_data_range(self, symbol: str, timeframe: str = "1m") -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        获取数据的时间范围
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            
        Returns:
            (开始时间, 结束时间)
        """
        try:
            metadata = self._load_metadata(symbol, timeframe)
            if metadata:
                start_time = datetime.fromisoformat(metadata.get('start_time', ''))
                end_time = datetime.fromisoformat(metadata.get('end_time', ''))
                return start_time, end_time
            return None, None
        except Exception as e:
            logger.error(f"获取数据范围失败: {e}")
            return None, None
    
    def delete_market_data(self, symbol: str, timeframe: str = "1m", 
                          start_time: Optional[datetime] = None, 
                          end_time: Optional[datetime] = None) -> bool:
        """
        删除市场数据
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            是否删除成功
        """
        try:
            symbol_path = os.path.join(self.data_dir, symbol.replace('/', '_'))
            timeframe_path = os.path.join(symbol_path, timeframe)
            
            if not os.path.exists(timeframe_path):
                return True
            
            if start_time and end_time:
                # 删除指定时间范围的数据
                start_date = start_time.date()
                end_date = end_time.date()
                date_range = pd.date_range(start=start_date, end=end_date)
                
                for date in date_range:
                    date_str = date.strftime('%Y%m%d')
                    file_path = os.path.join(timeframe_path, f"{date_str}.parquet")
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                # 删除所有数据
                import shutil
                shutil.rmtree(timeframe_path)
                os.makedirs(timeframe_path, exist_ok=True)
            
            # 更新元数据
            self._update_metadata(symbol, timeframe)
            
            # 重建索引
            self._build_index(symbol, timeframe)
            
            logger.info(f"删除市场数据成功: {symbol} {timeframe}")
            return True
        except Exception as e:
            logger.error(f"删除市场数据失败: {e}")
            return False
    
    def optimize_storage(self, symbol: str, timeframe: str = "1m") -> bool:
        """
        优化存储
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            
        Returns:
            是否优化成功
        """
        try:
            # 加载所有数据
            start_time, end_time = self.get_data_range(symbol, timeframe)
            if not start_time or not end_time:
                return True
            
            data = self.load_market_data(symbol, start_time, end_time, timeframe)
            if data.empty:
                return True
            
            # 重新保存数据
            self.delete_market_data(symbol, timeframe)
            self.save_market_data(symbol, data, timeframe)
            
            logger.info(f"优化存储成功: {symbol} {timeframe}")
            return True
        except Exception as e:
            logger.error(f"优化存储失败: {e}")
            return False
    
    def _update_metadata(self, symbol: str, timeframe: str, data: Optional[pd.DataFrame] = None):
        """
        更新元数据
        """
        try:
            metadata_path = os.path.join(self.metadata_dir, f"{symbol.replace('/', '_')}_{timeframe}.json")
            
            metadata = {}
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
            
            if data is not None and not data.empty:
                metadata['start_time'] = data.index.min().isoformat()
                metadata['end_time'] = data.index.max().isoformat()
                metadata['record_count'] = len(data)
                metadata['columns'] = list(data.columns)
                metadata['last_updated'] = datetime.now().isoformat()
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"更新元数据失败: {e}")
    
    def _load_metadata(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        加载元数据
        """
        try:
            metadata_path = os.path.join(self.metadata_dir, f"{symbol.replace('/', '_')}_{timeframe}.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载元数据失败: {e}")
            return {}
    
    def _build_index(self, symbol: str, timeframe: str):
        """
        构建索引
        """
        try:
            index_path = os.path.join(self.index_dir, f"{symbol.replace('/', '_')}_{timeframe}.json")
            
            symbol_path = os.path.join(self.data_dir, symbol.replace('/', '_'))
            timeframe_path = os.path.join(symbol_path, timeframe)
            
            if not os.path.exists(timeframe_path):
                return
            
            # 收集所有文件的时间范围
            file_index = {}
            for file_name in os.listdir(timeframe_path):
                if file_name.endswith('.parquet'):
                    date_str = file_name.split('.')[0]
                    file_path = os.path.join(timeframe_path, file_name)
                    
                    # 读取文件的时间范围
                    table = pq.read_table(file_path)
                    df = table.to_pandas()
                    if not df.empty:
                        start_time = df.index.min().isoformat()
                        end_time = df.index.max().isoformat()
                        file_index[date_str] = {
                            'start_time': start_time,
                            'end_time': end_time,
                            'record_count': len(df)
                        }
            
            # 保存索引
            with open(index_path, 'w') as f:
                json.dump(file_index, f, indent=2)
        except Exception as e:
            logger.error(f"构建索引失败: {e}")
    
    def close(self):
        """
        关闭资源
        """
        self.executor.shutdown()
        logger.info("数据存储系统已关闭")

# 使用示例
if __name__ == "__main__":
    # 创建数据存储实例
    storage = EnhancedDataStorage()
    
    # 生成测试数据
    date_rng = pd.date_range(start='2024-01-01', end='2024-01-02', freq='1min')
    test_data = pd.DataFrame(
        {
            'open': np.random.rand(len(date_rng)) * 10000 + 40000,
            'high': np.random.rand(len(date_rng)) * 1000 + 40500,
            'low': np.random.rand(len(date_rng)) * 1000 + 39500,
            'close': np.random.rand(len(date_rng)) * 10000 + 40000,
            'volume': np.random.rand(len(date_rng)) * 1000000
        },
        index=date_rng
    )
    
    # 保存数据
    storage.save_market_data('BTC/USDT', test_data, '1m')
    
    # 加载数据
    loaded_data = storage.load_market_data('BTC/USDT', 
                                         datetime(2024, 1, 1, 0, 0, 0), 
                                         datetime(2024, 1, 1, 23, 59, 59), 
                                         '1m')
    logger.info(f"加载的数据行数: {len(loaded_data)}")
    
    # 获取可用交易对
    symbols = storage.get_available_symbols()
    logger.info(f"可用交易对: {symbols}")
    
    # 获取可用时间周期
    timeframes = storage.get_available_timeframes('BTC/USDT')
    logger.info(f"可用时间周期: {timeframes}")
    
    # 获取数据范围
    start_time, end_time = storage.get_data_range('BTC/USDT', '1m')
    logger.info(f"数据范围: {start_time} 到 {end_time}")
    
    # 优化存储
    storage.optimize_storage('BTC/USDT', '1m')
    
    # 关闭资源
    storage.close()
