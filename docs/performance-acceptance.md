# Runtime 性能验收

在 Windows 本机使用默认监控组合进行短时空闲采样：先预热 3 秒，再采样 10 秒。

| 指标 | 结果 | 目标 |
| --- | ---: | ---: |
| CPU 平均值 | 1.72% | < 3% |
| CPU 峰值 | 12.5% | 观察项，启动/扫描瞬时峰值可接受 |
| RSS 内存峰值 | 30.27MB | < 250MB |

运行线程为进程、Coding Agent、窗口、文件刷新和事件分发线程；没有额外的 Codex CLI 轮询线程。通用进程扫描使用轻量 `pid/name` 查询，Coding Agent 监控只对匹配的 Codex/Claude 进程补取 `create_time`。
