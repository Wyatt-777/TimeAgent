# Codex Integration Audit

> 审计日期：2026-08-26  
> 项目：Local PC Agent / Personal Observer Agent  
> 基线提交：`fd315eb feat: bootstrap local pc agent v0.1`

## 审计结论

当前项目已经完成 v0.1 的本地事件监控基础，但还没有进入 v0.2 或 v0.3。因此暂不进入 C1（Alert + Notification）、C2（MCP）或 C3（Plugin）。

推荐执行顺序：

```text
C0 Audit
  ↓
v0.2 Minimal LLM Brain
  ↓
v0.3 Coding Agent Monitor
  ↓
C1 Alert + Notification
  ↓
C2 Observer MCP
  ↓
C3 Codex Plugin
  ↓
C4 Lifecycle Hooks
  ↓
C5 Read-only Investigation
```

## 1. 仓库状态

- 本地仓库：`D:/trackTime/local-pc-agent`
- 远程仓库：`https://github.com/Wyatt-777/TimeAgent.git`
- 当前分支：`master`
- 本地与远程：`master...origin/master`
- 工作区：审计开始时干净
- 测试：`30 passed`
- v0.1 短时稳定性测试：已通过
- 正式项目级长时验收：按当前项目约定延期到整体功能完成后

## 2. 原方案版本映射

| 阶段 | 状态 | 证据 |
|---|---|---|
| v0.1 Sensor Runtime | 已完成阶段实现 | Event、Bus、Store、三类 Monitor、Rule、Dispatcher、Lifecycle 已存在 |
| v0.2 LLM Brain | 未开始 | `agent/` 目前只有占位初始化文件 |
| v0.3 Coding Agent Monitor | 未开始 | 尚无 Coding Session、项目关联、Git/Test 聚合模块 |
| v0.4 Screen Vision | 未开始 | `vision/` 只有占位初始化文件 |
| v0.5 Memory | 未开始 | `memory/` 只有占位初始化文件 |
| v0.6 Computer Control | 未开始 | 未实现控制工具和审批流程 |

## 3. 当前核心能力

已实现模块：

- `core/event.py`：统一 Event Schema、EventType、Priority、JSON 序列化。
- `core/event_bus.py`：线程安全队列、发布、消费和关闭。
- `core/event_store.py`：SQLite `events` 表、写入、查询和索引。
- `core/rule_engine.py`：IGNORE、STORE、ANALYZE、ALERT 分类。
- `core/dispatcher.py`：Sensor → Bus → Rule → Store 链路。
- `core/lifecycle.py`：启动、停止、排空队列和 Graceful Shutdown。
- `sensors/process_monitor.py`：进程启动/结束检测。
- `sensors/file_monitor.py`：限定目录、忽略规则和 debounce。
- `sensors/window_monitor.py`：活动窗口标题变化检测。

当前 SQLite 只包含：

```text
events
idx_events_timestamp
idx_events_type
idx_events_source
idx_events_priority
```

尚未包含：

```text
sessions
alerts
notifications
agent_runs
tool_calls
hook_events
approvals
```

## 4. 架构缺口

升级方案要求但当前不存在的模块：

- `notifications/`
- `alerts/`
- `workspace/`
- `integrations/mcp/`
- `integrations/codex/`
- `agent/router.py`
- `agent/importance.py`
- `agent/investigation.py`
- `sensors/system_monitor.py`
- `sensors/coding_agent_monitor.py`

重要设计缺口：

1. 尚无数据库迁移机制；在加入 alerts、sessions 和 agent audit 表前必须先建立迁移入口。
2. EventType 当前是严格枚举；新增 Codex Session、测试和 Git 事件时要同步更新 Schema 与兼容测试。
3. Workspace Resolver 尚不存在，MCP 和 Codex Investigation 不能猜测项目路径。
4. Dispatcher 虽有 `on_analyze` / `on_alert` 回调，但还没有 Alert Service 和 Notification Service。
5. 当前配置中的 `system_monitor` 只有设置模型，没有对应 Sensor 实现。

## 5. Codex 本机能力审计

### 已验证

- Windows 桌面包：`OpenAI.Codex 26.818.8289.0`。
- 本机 Codex 配置存在 `mcp_servers` 和插件配置区域。
- 当前配置存在 `node_repl` MCP。
- 当前已安装 OpenAI Bundled / Primary Runtime 插件缓存。
- 当前没有项目级或用户级已配置 Hooks 事件。

### 未验证 / 当前限制

- `codex.exe` 位于 Windows App 安装目录，从当前 PowerShell 直接运行返回“拒绝访问”，因此独立 CLI 版本和 `codex mcp` 命令尚未完成实机验证。
- MCP 手工连接测试应优先通过 Codex 桌面 App 的 MCP 设置完成；后续若需要 CLI 自动化，再单独解决 CLI 入口。
- 当前没有已安装的 Personal Observer Plugin。

### 官方能力边界

官方文档确认 Plugin 使用 `.codex-plugin/plugin.json`，可组合 Skills、MCP Server 和可选生命周期 Hooks。官方文档也确认本地 Codex 支持 STDIO / Streamable HTTP MCP，以及 `SessionStart`、`SessionEnd`、`PreToolUse`、`PostToolUse`、`Stop` 等 Hooks。

因此升级方案中的 `CODEX_TURN_STARTED`、`CODEX_TURN_FINISHED` 不能直接视为现成 Hook 事件，必须先由 Hook Adapter 根据实际输入映射，或由 Observer 自己推导。

## 6. C0 产出与 Go/No-Go

### C0 已完成

- 仓库状态审计。
- v0.1 / v0.2 / v0.3 映射。
- Event Schema 和 SQLite Schema 核对。
- Codex 桌面包、MCP、Plugin、Hooks 能力核对。
- 架构缺口和执行顺序确定。

### 当前 Go/No-Go

```text
允许：
  v0.2 Minimal LLM Brain
  数据库迁移基础
  纯 Mock / 离线测试

暂缓：
  C1 Notification
  C2 MCP
  C3 Plugin
  C4 Hooks
  C5 Investigation
  auto_investigate
  自动写代码
```

## 7. 下一批任务

1. 建立 SQLite migration 基础，并保持现有 `events` 表兼容。
2. 实现 v0.2 Task 101：`LLMProvider` 接口。
3. 实现 `MockProvider`，不依赖网络和真实 API。
4. 增加 Provider、超时、失败降级测试。
5. 保持 `agent_brain.enabled=false`，确认 LLM 不可用时 Runtime 仍可运行。

## 8. 安全约束

- Observer 不能依赖 Codex 进程、Codex UI 或在线 API。
- Plugin 不能持有核心业务状态。
- MCP 第一版只允许只读工具。
- Hook 只能增强 Session 信号，不能成为后台监听单点依赖。
- Investigation 第一版必须 read-only、有限时、可审计，且默认关闭。
- 不自动修改文件、commit、push、安装软件或发送外部消息。
