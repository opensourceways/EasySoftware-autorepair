#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) openEuler. 2025. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN 'AS IS' BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************
import unittest
from unittest.mock import MagicMock, patch
import asyncio
from app.config import settings
from app.utils.processor import RequestProcessor, REPAIR_STATUS_COMPLETED, REPAIR_STATUS_FAILED

# 模拟配置
settings.check_interval = 1  # 缩短检查间隔便于测试
settings.thread_pool_size = 2

class TestRequestProcessor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 模拟数据库连接池
        self.mock_db_pool = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        
        # 设置模拟对象行为
        self.mock_db_pool.get_connection.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor
        
        # 初始化被测对象
        self.processor = RequestProcessor()
        self.processor.db_pool = self.mock_db_pool
        self.processor.task_queue = asyncio.Queue()

    async def test_initialization(self):
        """测试初始化是否正确创建线程池"""
        # 验证线程池创建
        self.assertEqual(len(asyncio.all_tasks()), settings.thread_pool_size)
        
        # 验证数据库连接池初始化
        self.mock_db_pool.get_connection.assert_called_once()

    async def test_process_pending_requests_normal_flow(self):
        """测试正常处理挂起请求流程"""
        # 模拟数据库返回2条pending请求
        mock_requests = [
            (1, 'repo1', 'source1', 123, 'repo_name1', 'pr_url1', 'spec1'),
            (2, 'repo2', 'source2', 456, 'repo_name2', 'pr_url2', 'spec2')
        ]
        self.mock_cursor.fetchall.return_value = mock_requests
        
        # 执行测试方法
        await self.processor.process_pending_requests()
        
        # 验证状态更新
        self.mock_cursor.execute.assert_any_call(
            "UPDATE pending_requests SET status = 'processing' WHERE id IN (%s,%s)",
            ['1', '2']
        )
        
        # 验证任务提交
        self.assertEqual(self.processor.task_queue.qsize(), 2)

    async def test_process_pending_requests_no_requests(self):
        """测试无挂起请求时的处理"""
        self.mock_cursor.fetchall.return_value = []
        
        await self.processor.process_pending_requests()
        
        # 验证没有执行更新操作
        self.mock_cursor.execute.assert_not_called()

    async def test_process_request_success(self):
        """测试成功处理请求"""
        # 模拟修复处理成功
        with patch('your_module.process_initial_repair', return_value=None) as mock_repair:
            await self.processor.process_request(1, {'spec_content': 'valid_spec'})
            
            # 验证状态更新
            self.mock_cursor.execute.assert_any_call(
                "UPDATE pending_requests SET status = 'completed' WHERE id = %s",
                (1,)
            )
            mock_repair.assert_called_once()

    async def test_process_request_failure(self):
        """测试处理请求失败"""
        # 模拟修复处理抛出异常
        with patch('your_module.process_initial_repair', side_effect=Exception("Test error")):
            await self.processor.process_request(1, {'spec_content': 'invalid_spec'})
            
            # 验证状态更新为failed
            self.mock_cursor.execute.assert_any_call(
                "UPDATE pending_requests SET status = 'failed' WHERE id = %s",
                (1,)
            )

    async def test_repair_handler_success(self):
        """测试修复处理器成功路径"""
        with patch('your_module.process_initial_repair', return_value=None):
            result = await self.processor.repair_handler({'spec_content': 'valid'})
            self.assertEqual(result, REPAIR_STATUS_COMPLETED)

    async def test_repair_handler_failure(self):
        """测试修复处理器失败路径"""
        with patch('your_module.process_initial_repair', side_effect=Exception("Test error")):
            result = await self.processor.repair_handler({'spec_content': 'invalid'})
            self.assertEqual(result, REPAIR_STATUS_FAILED)

    async def test_concurrent_processing(self):
        """测试并发处理能力"""
        # 添加多个任务到队列
        for i in range(5):
            await self.processor.task_queue.put((i, {}))
        
        # 等待所有worker处理完成
        await asyncio.sleep(0.1)  # 等待事件循环处理
        
        # 验证队列清空
        self.assertEqual(self.processor.task_queue.qsize(), 0)
        self.assertTrue(self.processor.task_queue.empty())

    async def test_database_rollback_on_error(self):
        """测试数据库事务回滚"""
        # 强制触发数据库异常
        self.mock_cursor.execute.side_effect = Exception("Database error")
        
        with self.assertLogs() as captured:
            await self.processor.process_pending_requests()
            
            # 验证回滚和日志记录
            self.assertIn("Database error", captured.output[0])
            self.mock_conn.rollback.assert_called_once()

    async def test_task_queue_error_handling(self):
        """测试任务队列异常处理"""
        # 创建会抛出异常的任务
        async def failing_task():
            raise ValueError("Task failed")
        
        # 提交异常任务
        await self.processor.task_queue.put(failing_task())
        
        # 等待worker处理
        await asyncio.sleep(0.1)
        
        # 验证任务完成（即使失败）
        self.assertTrue(self.processor.task_queue.empty())