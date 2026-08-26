# Coding Agent 会话摘要闭环

当 `CodingAgentMonitor` 发布 `CODING_SESSION_FINISHED` 后，Runtime 会：

1. 从结束事件恢复会话元数据。
2. 仅在配置的工作区内读取 Git status 和 diff 统计。
3. 在同一显式工作区内运行受超时限制的 pytest。
4. 使用确定性的 `SessionSummaryBuilder` 生成摘要。
5. 发送一次本地通知；Git 或测试查询失败时保留部分摘要，Runtime 不退出。

该流程不会修改文件、提交或推送 Git，也不会调用 LLM。工作区路径无法解析时不会执行 Git 或测试命令。
