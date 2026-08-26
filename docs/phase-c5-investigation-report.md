# Phase C5 Investigation 进度记录

## 已完成：C501-C504

- C501：增加 `InvestigationTask` 模型，包含触发事件、显式项目路径、失败原因、状态流转和时间戳。
- C502：增加 `CodexLauncher`，使用固定的 `codex exec` 调用封装，避免调用方自行拼接命令。
- C503：增加 `ReadOnlySandboxPolicy`，强制 `--sandbox read-only`、`--ask-for-approval never`、`--ephemeral` 和 JSONL 输出，拒绝危险 bypass 参数。
- C504：增加有界 `InvestigationContextPackage`，提供触发事件、最近事件、Git 状态、diff 统计和测试结果，并明确只读调查边界。
- Launcher 失败、超时和输出长度均有边界处理；当前未接入自动 Investigation 调度。

## 尚未完成：C505-C510

下一批需要实现结构化结果解析、超时/调用次数限制、调查专用 Audit Log、手动审批模式和“重复测试失败调查”端到端闭环。当前 C5 不会自动修改文件、提交、推送或发送外部消息。
