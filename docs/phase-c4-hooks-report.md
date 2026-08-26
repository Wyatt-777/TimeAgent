# Phase C4 Hooks 进度记录

## 已完成：C401-C406、C408

- C401：增加 Codex Hooks 能力探测器，调用本机 `codex features list` 检查 `hooks` 是否启用，并记录 Codex 版本和支持事件集合。
- C402：增加 `HookAdapter`，将 Codex Hook stdin JSON 转换为统一 `Event`。
- C403-C404：插件提供 `SessionStart` 和 `SessionEnd` 命令 Hook，写入统一会话生命周期事件。
- C405：优先记录 Codex Hook 提供的 `cwd`，并支持 `LOCAL_PC_AGENT_ROOT` 与 `LOCAL_PC_AGENT_DATABASE` 显式定位。
- C406：Hook 入口只依赖 Python 标准库，任何解析、定位、数据库或适配错误都会记录到 stderr 并以退出码 0 返回，不阻断 Codex。
- 当前支持的事件映射包括会话开始/结束、回合开始/结束、工具活动、压缩和子 Agent 活动。
- 适配器只保留 `session_id`、`cwd`、工具名称、回合标识等安全元数据，不保存 `transcript_path`、`tool_input` 或 `tool_response`。
- Hooks 禁用时适配器为 no-op；探测失败或 Hook 不可用不会影响核心 Runtime。
- C408：完成安装缓存副本的插件校验，并真实执行安装副本的 `SessionStart`/`SessionEnd` Hook 入口，确认临时 SQLite 收到两类事件；测试结束后已卸载插件并清理临时市场、缓存和数据库。

本机验证结果：Codex CLI `0.150.0-alpha.8` 的 `hooks` 功能为 `stable / true`，C4 Hook 单元测试和插件 Hook 结构测试通过。

## C407：跨来源 Session 合并

已增加 `SessionMerger`，按 Hook 的 `cwd` 是否位于进程 Session 的项目路径内，并结合可配置时间窗口进行最佳匹配。匹配成功时 Observer MCP 返回一条逻辑 Session 并附带两个来源；匹配失败时保留 Hook-only 或 process-only 记录；已结束的 Hook Session 不会继续显示为活动 Session。重复 Hook 生命周期事件仍通过稳定 event id + `INSERT OR IGNORE` 幂等去重。

当前适配器尚未自动修改 Codex 用户配置，也不会让 Hook 成为 Observer 的单点依赖。
