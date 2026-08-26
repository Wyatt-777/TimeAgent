# Phase C5 Investigation 进度记录

## 已完成：C501-C510

- C501：增加 `InvestigationTask` 模型，包含触发事件、显式项目路径、失败原因、状态流转和时间戳。
- C502：增加 `CodexLauncher`，使用固定的 `codex exec` 调用封装，避免调用方自行拼接命令。
- C503：增加 `ReadOnlySandboxPolicy`，强制 `--sandbox read-only`、`--ask-for-approval never`、`--ephemeral` 和 JSONL 输出，拒绝危险 bypass 参数。
- C504：增加有界 `InvestigationContextPackage`，提供触发事件、最近事件、Git 状态、diff 统计和测试结果，并明确只读调查边界。
- C505：增加严格 `InvestigationResult` 解析，支持单 JSON、JSON fence 和 Codex JSONL 最后一条结果。
- C506：Launcher 已提供超时状态、受限输出和失败转换。
- C507：增加滚动时间窗口调用次数限制，默认每小时最多 3 次。
- C508：调查结果写入现有 Audit Log，只保存结构化结果和任务元数据，不保存原始模型输出。
- C509：默认手动审批；未审批任务不会启动 Codex。
- C510：完成“重复测试失败调查”本地端到端测试，确认只读参数、结构化根因结果和审计记录均生效。
- 现已接入 Alert 链路：重复测试失败告警只创建待处理调查任务；必须显式批准后才会启动 Codex，结果会回写 Alert metadata。
- 用户批准调查并完成后，Runtime 会发送一次独立的结果通知；该通知不受原告警冷却影响，也不会覆盖告警当前状态。

当前未接入自动 Investigation 调度。C5 不会自动修改文件、提交、推送或发送外部消息。
