"""
并行数据处理引擎 - 高性能数据并行处理

功能：
1. 多进程/多线程并行数据处理
2. 数据流管道和批处理
3. 内存池和缓存优化
4. 实时数据流处理
5. 数据压缩和序列化优化
"""

import asyncio
import concurrent.futures
import logging
import multiprocessing as mp
import pickle
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Empty, Queue
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union

import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ProcessingMode(Enum):
    """处理模式"""
    SYNC = "sync"           # 同步处理
    THREAD = "thread"       # 多线程
    PROCESS = "process"     # 多进程
    ASYNC = "async"         # 异步处理


class DataFormat(Enum):
    """数据格式"""
    RAW = "raw"
    PANDAS = "pandas"
    NUMPY = "numpy"
    ARROW = "arrow"


@dataclass
class ProcessingTask:
    """处理任务"""
    id: str
    data: Any
    processor: Callable
    callback: Optional[Callable] = None
    priority: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    timeout: Optional[float] = None


@dataclass
class ProcessingResult:
    """处理结果"""
    task_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    processing_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


class MemoryPool:
    """内存池管理"""
    
    def __init__(self, max_size: int = 1000, object_size: int = 1024):
        self.max_size = max_size
        self.object_size = object_size
        self._pool: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._stats = {
            "allocations": 0,
            "deallocations": 0,
            "hits": 0,
            "misses": 0
        }
    
    def acquire(self) -> Any:
        """获取内存对象"""
        with self._lock:
            if self._pool:
                self._stats["hits"] += 1
                return self._pool.pop()
            else:
                self._stats["misses"] += 1
                self._stats["allocations"] += 1
                return bytearray(self.object_size)
    
    def release(self, obj: Any):
        """释放内存对象"""
        with self._lock:
            if len(self._pool) < self.max_size:
                self._pool.append(obj)
            self._stats["deallocations"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()


class DataPipeline:
    """数据流管道"""
    
    def __init__(self, name: str = "pipeline"):
        self.name = name
        self.stages: List[Dict[str, Any]] = []
        self._running = False
        self._queues: List[asyncio.Queue] = []
        self._tasks: List[asyncio.Task] = []
    
    def add_stage(self, 
                  processor: Callable,
                  mode: ProcessingMode = ProcessingMode.ASYNC,
                  workers: int = 1,
                  buffer_size: int = 1000):
        """添加处理阶段"""
        self.stages.append({
            "processor": processor,
            "mode": mode,
            "workers": workers,
            "buffer_size": buffer_size
        })
    
    async def initialize(self):
        """初始化管道"""
        # 为每个阶段创建队列
        for stage in self.stages:
            queue = asyncio.Queue(maxsize=stage["buffer_size"])
            self._queues.append(queue)
        
        # 添加输出队列
        self._queues.append(asyncio.Queue())
        
        self._running = True
        
        # 启动处理任务
        for i, stage in enumerate(self.stages):
            for _ in range(stage["workers"]):
                task = asyncio.create_task(
                    self._stage_worker(i, stage, self._queues[i], self._queues[i+1])
                )
                self._tasks.append(task)
        
        logger.info(f"数据管道 {self.name} 初始化完成，{len(self.stages)} 个阶段")
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        self._queues.clear()
    
    async def _stage_worker(self, stage_idx: int, stage: Dict, 
                           input_queue: asyncio.Queue, output_queue: asyncio.Queue):
        """阶段工作线程"""
        processor = stage["processor"]
        mode = stage["mode"]
        
        while self._running:
            try:
                # 获取数据
                data = await asyncio.wait_for(input_queue.get(), timeout=1.0)
                
                # 处理数据
                start_time = time.time()
                
                if mode == ProcessingMode.ASYNC:
                    result = await processor(data)
                elif mode == ProcessingMode.SYNC:
                    result = processor(data)
                elif mode == ProcessingMode.THREAD:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, processor, data)
                
                processing_time = time.time() - start_time
                
                # 输出结果
                await output_queue.put({
                    "data": result,
                    "stage": stage_idx,
                    "processing_time": processing_time
                })
                
                input_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"阶段 {stage_idx} 处理错误: {e}")
    
    async def put(self, data: Any):
        """输入数据"""
        if self._queues:
            await self._queues[0].put(data)
    
    async def get(self) -> Any:
        """获取输出"""
        if self._queues:
            return await self._queues[-1].get()
        return None


class ParallelDataProcessor:
    """并行数据处理器"""
    
    def __init__(self, 
                 max_workers: int = None,
                 mode: ProcessingMode = ProcessingMode.THREAD):
        self.max_workers = max_workers or mp.cpu_count()
        self.mode = mode
        self._executor: Optional[Union[ThreadPoolExecutor, ProcessPoolExecutor]] = None
        self._memory_pool = MemoryPool()
        self._pipelines: Dict[str, DataPipeline] = {}
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_processing_time": 0.0
        }
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """初始化处理器"""
        if self._initialized:
            return
        
        # 创建执行器
        if self.mode == ProcessingMode.THREAD:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        elif self.mode == ProcessingMode.PROCESS:
            self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
        
        self._initialized = True
        logger.info(f"并行数据处理器初始化完成，模式: {self.mode.value}, 工作线程: {self.max_workers}")
    
    async def cleanup(self):
        """清理资源"""
        # 清理管道
        for pipeline in self._pipelines.values():
            await pipeline.cleanup()
        self._pipelines.clear()
        
        # 关闭执行器
        if self._executor:
            self._executor.shutdown(wait=True)
        
        self._initialized = False
        logger.info("并行数据处理器清理完成")
    
    async def process_batch(self, 
                           data_list: List[Any],
                           processor: Callable,
                           mode: Optional[ProcessingMode] = None) -> List[ProcessingResult]:
        """批量处理数据"""
        if not self._initialized:
            raise RuntimeError("处理器未初始化")
        
        use_mode = mode or self.mode
        start_time = time.time()
        
        async with self._lock:
            self._stats["total_tasks"] += len(data_list)
        
        if use_mode == ProcessingMode.SYNC:
            # 同步处理
            results = []
            for data in data_list:
                try:
                    result_data = processor(data)
                    results.append(ProcessingResult(
                        task_id=str(id(data)),
                        success=True,
                        data=result_data
                    ))
                except Exception as e:
                    results.append(ProcessingResult(
                        task_id=str(id(data)),
                        success=False,
                        error=str(e)
                    ))
        
        elif use_mode == ProcessingMode.ASYNC:
            # 异步处理
            tasks = []
            for data in data_list:
                task = asyncio.create_task(self._async_process(data, processor))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [r if isinstance(r, ProcessingResult) else 
                      ProcessingResult(task_id="", success=False, error=str(r))
                      for r in results]
        
        else:
            # 线程/进程池处理
            loop = asyncio.get_event_loop()
            futures = []
            
            for data in data_list:
                future = loop.run_in_executor(self._executor, processor, data)
                futures.append(future)
            
            raw_results = await asyncio.gather(*futures, return_exceptions=True)
            
            results = []
            for i, result in enumerate(raw_results):
                if isinstance(result, Exception):
                    results.append(ProcessingResult(
                        task_id=str(id(data_list[i])),
                        success=False,
                        error=str(result)
                    ))
                else:
                    results.append(ProcessingResult(
                        task_id=str(id(data_list[i])),
                        success=True,
                        data=result
                    ))
        
        # 更新统计
        processing_time = time.time() - start_time
        async with self._lock:
            self._stats["completed_tasks"] += sum(1 for r in results if r.success)
            self._stats["failed_tasks"] += sum(1 for r in results if not r.success)
            self._stats["total_processing_time"] += processing_time
        
        return results
    
    async def _async_process(self, data: Any, processor: Callable) -> ProcessingResult:
        """异步处理单个数据"""
        task_id = str(id(data))
        start_time = time.time()
        
        try:
            if asyncio.iscoroutinefunction(processor):
                result_data = await processor(data)
            else:
                result_data = processor(data)
            
            return ProcessingResult(
                task_id=task_id,
                success=True,
                data=result_data,
                processing_time=time.time() - start_time
            )
        except Exception as e:
            return ProcessingResult(
                task_id=task_id,
                success=False,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    def create_pipeline(self, name: str) -> DataPipeline:
        """创建数据管道"""
        pipeline = DataPipeline(name)
        self._pipelines[name] = pipeline
        return pipeline
    
    async def process_dataframe(self, 
                               df: pd.DataFrame,
                               processor: Callable,
                               chunk_size: int = 1000) -> pd.DataFrame:
        """并行处理DataFrame"""
        if len(df) <= chunk_size:
            # 小数据量直接处理
            return processor(df)
        
        # 分块处理
        chunks = [df[i:i+chunk_size] for i in range(0, len(df), chunk_size)]
        
        # 并行处理各块
        results = await self.process_batch(chunks, processor)
        
        # 合并结果
        successful_results = [r.data for r in results if r.success and r.data is not None]
        
        if successful_results:
            return pd.concat(successful_results, ignore_index=True)
        else:
            return pd.DataFrame()
    
    async def process_numpy_array(self,
                                 arr: np.ndarray,
                                 processor: Callable,
                                 axis: int = 0) -> np.ndarray:
        """并行处理NumPy数组"""
        # 沿指定轴分割数组
        chunks = np.array_split(arr, self.max_workers, axis=axis)
        
        # 并行处理
        results = await self.process_batch(chunks, processor)
        
        # 合并结果
        successful_results = [r.data for r in results if r.success and r.data is not None]
        
        if successful_results:
            return np.concatenate(successful_results, axis=axis)
        else:
            return np.array([])
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        if stats["total_tasks"] > 0:
            stats["success_rate"] = stats["completed_tasks"] / stats["total_tasks"]
            stats["avg_processing_time"] = stats["total_processing_time"] / stats["total_tasks"]
        else:
            stats["success_rate"] = 0.0
            stats["avg_processing_time"] = 0.0
        
        stats["memory_pool"] = self._memory_pool.get_stats()
        return stats


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建处理器
    processor = ParallelDataProcessor(max_workers=4, mode=ProcessingMode.THREAD)
    await processor.initialize()
    
    try:
        # 定义处理函数
        def process_data(data: Dict) -> Dict:
            """处理数据"""
            # 模拟耗时操作
            time.sleep(0.01)
            return {
                "input": data,
                "output": data["value"] * 2,
                "processed": True
            }
        
        # 准备测试数据
        test_data = [{"id": i, "value": i * 10} for i in range(100)]
        
        # 批量处理
        start_time = time.time()
        results = await processor.process_batch(test_data, process_data)
        elapsed = time.time() - start_time
        
        print(f"处理 {len(test_data)} 条数据，耗时: {elapsed:.3f}秒")
        print(f"成功率: {sum(1 for r in results if r.success) / len(results) * 100:.1f}%")
        
        # 处理DataFrame
        df = pd.DataFrame({
            "A": range(10000),
            "B": range(10000, 20000)
        })
        
        def process_df(chunk: pd.DataFrame) -> pd.DataFrame:
            chunk["C"] = chunk["A"] + chunk["B"]
            return chunk
        
        result_df = await processor.process_dataframe(df, process_df, chunk_size=1000)
        print(f"DataFrame处理完成，形状: {result_df.shape}")
        
        # 获取统计
        stats = processor.get_stats()
        print(f"统计信息: {stats}")
        
    finally:
        await processor.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
