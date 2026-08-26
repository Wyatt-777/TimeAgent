from agent.audit_log import AuditLog, AuditRecord
from agent.decision import DecisionImportance, StructuredDecision
from agent.executor import ActionExecutor, ExecutionStatus


def decision(action: str) -> StructuredDecision:
    return StructuredDecision(
        importance=DecisionImportance.HIGH,
        summary="Repeated test failure",
        next_action=action,
    )


def test_executor_writes_blocked_attempt_to_jsonl_audit_log(tmp_path) -> None:
    path = tmp_path / "audit" / "agent.jsonl"
    audit = AuditLog(path)
    result = ActionExecutor(audit_log=audit).execute(
        decision("delete_file"),
        trigger="test_failure_alert",
        audit_metadata={"project_path": "D:/project"},
    )

    assert result.execution_status is ExecutionStatus.BLOCKED
    records = audit.records()
    assert len(records) == 1
    assert records[0].action == "delete_file"
    assert records[0].approval_status == "requires_approval"
    assert records[0].execution_status == "blocked"
    assert records[0].trigger == "test_failure_alert"
    assert records[0].metadata == {"project_path": "D:/project"}
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_audit_log_reloads_records_from_disk(tmp_path) -> None:
    path = tmp_path / "agent.jsonl"
    first = AuditLog(path)
    record = AuditRecord(action="git_status", summary="inspect repository")
    first.append(record)

    second = AuditLog(path)

    assert second.records() == (record,)


def test_audit_log_returns_bounded_tail() -> None:
    audit = AuditLog()
    audit.append(AuditRecord(summary="one"))
    audit.append(AuditRecord(summary="two"))

    assert [item.summary for item in audit.records(limit=1)] == ["two"]
