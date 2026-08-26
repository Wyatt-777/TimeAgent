# Runtime 配置开关

`config/default.yaml` 提供当前安全默认值：

- `codex.investigation.enabled` 控制是否为重复测试失败创建调查任务。
- `codex.investigation.mode` 固定为 `read_only`；其他模式会被拒绝。
- `codex.investigation.timeout_seconds`、`max_invocations` 和 `window_seconds` 控制调查边界。
- `codex.investigation.auto_investigate` 默认关闭；当前版本不会因告警自动启动 Codex。
- `notifications.enabled`、`minimum_priority`、`cooldown_seconds` 和 `dedup_window_seconds` 控制告警通知。
- `proactive_agent.enabled` 和 `notify_on` 控制会话完成摘要通知。

未填写新配置段时，系统使用兼容旧版本的默认值。高风险动作审批策略不受这些开关绕过。
