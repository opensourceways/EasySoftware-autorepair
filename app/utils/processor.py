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
# ******************************************************************************/
import logging
import asyncio

from app.config import settings, init_db_pool
from app.api.endpoints.webhook import process_initial_repair


REPAIR_STATUS_COMPLETED = "completed"
REPAIR_STATUS_FAILED = "failed"
REPAIR_STATUS_PROCESSING = "processing"
REPAIR_STATUS_PENDING = "pending"

logger = logging.getLogger(__name__)


class RequestProcessor:
    def __init__(self):
        """
        初始化数据库连接池和线程池。
        """
        self.db_pool = init_db_pool()
        self.check_interval = settings.check_interval
        self.task_queue = asyncio.Queue()
        for _ in range(settings.thread_pool_size):
            asyncio.create_task(self.worker())

    async def worker(self):
        """工作者协程持续处理队列中的任务
    
        该协程不断从任务队列中获取请求数据，并尝试处理这些请求。
        如果处理过程中发生错误，确保任务被标记为已完成，以维护队列的正确性。
        """
        while True:
            request_data = await self.task_queue.get()
            try:
                await self.process_request(request_data[0], request_data[1])
            finally:
                self.task_queue.task_done()

    async def start(self):
        """
        启动后台任务。
        """
        while True:
            await self.process_pending_requests()
            await asyncio.sleep(self.check_interval)
    
    async def process_pending_requests(self):
        """
        处理挂起的请求。该方法从数据库中获取状态为'pending'或'failed'的请求，
        将其标记为'processing'，并提交到线程池中异步处理。
        """
        try:
            
            conn = self.db_pool.get_connection()
            cursor = conn.cursor()
            
            # 使用事务 + FOR UPDATE锁定记录
            cursor.execute("""
                SELECT id, repo_url, source_url, pr_number, repo_name, pr_url, spec_content 
                FROM pending_requests 
                WHERE (status = 'pending' or status = 'failed')
                LIMIT 8
                FOR UPDATE;
            """)
            
            requests = cursor.fetchall()
            if not requests:
                conn.commit()
                return
            # 更新状态为processing
            update_ids = [str(r[0]) for r in requests]
            cursor.execute(
                "UPDATE pending_requests SET status = 'processing' "
                f"WHERE id IN ({','.join(['%s'] * len(update_ids))})",
                update_ids
            )
            conn.commit()
            # 提交任务创建协程
            tasks = []
            for req in requests:
                logger.info(f"{req[4]}提交任务创建协程")
                request_data = {
                    "repo_url": req[1],
                    "source_url": req[2],
                    "pr_number": req[3],
                    "repo_name": req[4],
                    "pr_url": req[5],
                    "spec_content": req[6]
                }
                tasks.append(self.task_queue.put((req[0], request_data))) 
            await asyncio.gather(*tasks)  # 最后统一等待所有任务完成
  
        except Exception as e:
            conn.rollback()
            logger.info(f"Database error: {e}")
        finally:
            cursor.close()
            conn.close()
    
    async def process_request(self, request_id, request_data):
        """
        处理请求函数

        本函数接收请求ID和请求数据作为参数，尝试执行业务逻辑并更新数据库中的请求状态

        参数:
        request_id (int): 请求的唯一标识符
        request_data (dict): 包含请求详细信息的字典

        返回:
        无
        """
        try:
            # 业务逻辑
            taskStatus = await self.repair_handler(request_data)
            logger.info(f"处理完毕 开始数据回库")
            conn = self.db_pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_requests SET status = %s WHERE id = %s",
                (taskStatus, request_id)
            )
            conn.commit()
            logger.info(f"处理完毕 数据回库成功")
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            conn.rollback()
            cursor.execute(
                "UPDATE pending_requests SET status = 'failed' WHERE id = %s",
                (request_id)
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    async def repair_handler(self, request_data) -> str:
        """
        处理修复请求的数据。

        该函数从请求数据中提取必要的信息，组织成一个字典，并调用另一个函数来执行初始修复操作。

        参数:
        - request_data: 包含修复请求详细信息的字典，包括仓库URL、PR编号、规范内容等。

        返回:
        - 一个包含处理状态的字典，表示修复请求已被处理。
        """
        pr_data = {
            "repo_url": request_data["repo_url"],
            "source_url": request_data["source_url"],
            "pr_number": request_data["pr_number"],
            "repo_name": request_data["repo_name"],
            "pr_url": request_data["pr_url"],
        }
        spec_content = request_data["spec_content"]
        try:
            await process_initial_repair(pr_data, spec_content)
            return REPAIR_STATUS_COMPLETED
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            return REPAIR_STATUS_FAILED