# Personal Observer 插件安装测试记录

本记录对应 C3 C308-C309，用于确认 `personal-observer` 插件可以被 Codex CLI 安装、加载，并在与源码隔离的临时目录中完成基本校验。

## C308：插件安装与加载

- 使用一次性的本地测试市场安装 `personal-observer@personal`，没有修改默认个人插件市场。
- `codex plugin add` 返回安装成功且状态为 enabled。
- 对安装后的缓存副本运行 `validate_plugin.py`，校验通过。
- 从安装后的 `.mcp.json` 启动 MCP Server，`initialize` 和 `tools/list` 均成功。
- MCP Server 返回预期的 5 个只读工具：`get_status`、`get_recent_events`、`get_pending_alerts`、`get_active_sessions`、`get_git_status`。
- 测试结束后已卸载插件、移除临时测试市场并清理临时目录；安装缓存也已确认不存在。

## C309：隔离环境验证

- 将插件复制到独立临时目录，源码 `plugin.json` 与测试副本的 SHA-256 一致。
- 对隔离副本运行插件校验器，校验通过。
- 隔离副本可以独立读取 manifest、`.mcp.json` 并完成 MCP 握手，不依赖仓库中的 Python 虚拟环境。
- 仓库测试与 `main.py --once` 在插件卸载后仍可正常执行，证明插件安装测试没有改变核心 Runtime 状态。

本次 C309 是同一台 Windows 机器上的“干净环境式”隔离验证，不等同于另一台电脑或另一种操作系统上的完整发布验收。当前 `.mcp.json` 仍包含本机 Windows 路径；如果后续需要面向其他电脑分发插件，应再增加路径发现或安装时配置机制。
