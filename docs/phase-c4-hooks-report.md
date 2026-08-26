# Phase C4 Hooks 进度记录

## 已完成：C401-C402

- C401：增加 Codex Hooks 能力探测器，调用本机 `codex features list` 检查 `hooks` 是否启用，并记录 Codex 版本和支持事件集合。
- C402：增加 `HookAdapter`，将 Codex Hook stdin JSON 转换为统一 `Event`。
- 当前支持的事件映射包括会话开始/结束、回合开始/结束、工具活动、压缩和子 Agent 活动。
- 适配器只保留 `session_id`、`cwd`、工具名称、回合标识等安全元数据，不保存 `transcript_path`、`tool_input` 或 `tool_response`。
- Hooks 禁用时适配器为 no-op；探测失败或 Hook 不可用不会影响核心 Runtime。

本机验证结果：Codex CLI `0.150.0-alpha.8` 的 `hooks` 功能为 `stable / true`，C4 Hook 单元测试 6 项通过。

## 尚未完成：C403-C408

下一批需要接入实际的 `SessionStart`/`SessionEnd` 命令 Hook，补充 cwd 捕获、Hook 失败 fallback、进程监控 Session 与 Hook Session 的去重合并，并执行真实触发测试。当前适配器尚未自动修改 Codex 用户配置，也不会让 Hook 成为 Observer 的单点依赖。
