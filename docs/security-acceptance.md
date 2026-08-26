# Codex 集成安全验收

当前自动化边界：

- `delete_file`、`commit`、`push`、`install_package`、`send_message`、`kill_process` 和 `modify_system` 始终需要显式用户审批。
- 高风险动作即使被错误加入自定义自动允许列表，也不会获得自动执行资格。
- 未注册动作默认拒绝；已注册的高风险处理器也会在调用前被拦截。
- Investigation 使用只读沙箱，不允许修改文件、提交、推送、安装包或发送消息。
- Investigation 的审批、执行结果和失败原因写入 Audit Log。

验收覆盖：删除文件、Git push、安装包、发送消息、终止进程、系统修改、未注册命令、只读沙箱提示词和自动允许列表绕过尝试。
