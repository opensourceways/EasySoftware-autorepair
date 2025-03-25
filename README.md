## 活动图：

![autorepair活动图](https://github.com/user-attachments/assets/7cceecbe-2751-4b02-a58d-7916f6b52c04)

## 时序图

![autorepair时序图](https://github.com/user-attachments/assets/fabe0a26-3194-4159-a52b-841c5d234a29)

## 组件图

![autorepair组件图](https://github.com/user-attachments/assets/e592063f-9005-46e6-82bc-250f8634595d)


### 关键流程：

1. **签名验证**：使用HMAC-SHA256验证请求合法性
2. **智能分析**：通过SiliconFlow的AI模型分析构建日志
3. **自动修复**：动态生成新的spec文件并提交到fork仓库
4. **构建重试**：采用带指数退避的重试机制（代码中为固定间隔）
5. **状态追踪**：通过EulerMaker API持续监控构建状态

- 多层安全验证（HMAC签名+事件类型过滤）
- 异步任务处理架构
- AI驱动的自动修复循环
- 与第三方服务（GitLab/EulerMaker）的集成方式
