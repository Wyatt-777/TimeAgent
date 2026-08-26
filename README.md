# Local PC Agent

Local PC Agent 是一个运行在 Windows 本地电脑上的事件驱动型 Agent Runtime。

当前实现范围是 v0.1：先建立稳定、可测试的本地事件监控闭环，再逐步加入 LLM、视觉和电脑控制能力。

## 开发环境

- Windows 10 / Windows 11
- Python 3.11+
- Git

## 快速开始

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python main.py
```

快速启动检查：

```powershell
python main.py --once
```

当前已完成 v0.1 基础运行时、v0.2 Task 101-106、v0.3 Task 201-208、C1 Task 101-108、C2 Observer MCP 只读工具、C3 C301-C309 Plugin，以及 C4 C401-C406/C408 Hooks 能力探测、事件适配、Session Hook、cwd 捕获、失败 fallback 和集成验证：可替换的 LLM Provider 接口、离线 MockProvider、上下文构建器、结构化决策安全解析、默认拒绝的审批策略、受策略保护的动作执行器、Agent 调用审计日志、Coding Agent Session 识别与 SQLite 持久化、显式项目路径关联、只读 Git 状态查询、只读 Git diff 统计、受限测试运行、重复失败高优先级事件、只读 Session Summary、Alert Inbox 的重要性/去重/冷却/通知策略、Windows 本地通知适配器、Runtime 告警集成，以及 Observer MCP 的状态、事件、告警、Session 和 Git 状态查询。Agent Brain 默认仍关闭；当前阶段先执行 5 分钟短时验收，项目整体完成后再执行正式长时稳定性验收。

运行当前阶段的 5 分钟短测：

```powershell
python -m scripts.stability_test --hours 0.083333 --interval-seconds 30
```

最终完整验收时可以省略参数，默认运行 8 小时。日志会写入 `data/logs/`。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## v0.1 边界

v0.1 只实现进程、文件和活动窗口事件监控，以及事件存储、规则分类和优雅关闭。暂不实现 LLM、截图、鼠标键盘控制、浏览器自动化或高风险命令执行。
