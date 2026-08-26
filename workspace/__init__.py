"""Explicitly configured workspace resolution."""

from .resolver import Workspace, WorkspaceMatch, WorkspaceResolver
from .tests import TestRunResult, TestRunStatus, TestRunner, parse_pytest_summary
from .summary import CodingSessionSummary, SessionSummaryBuilder
from .git import (
    GitCommandError,
    GitDiffFile,
    GitDiffStat,
    GitInspector,
    GitStatus,
    parse_diff_numstat,
    parse_status,
)

__all__ = [
    "GitCommandError",
    "GitDiffFile",
    "GitDiffStat",
    "GitInspector",
    "GitStatus",
    "Workspace",
    "WorkspaceMatch",
    "WorkspaceResolver",
    "TestRunResult",
    "TestRunStatus",
    "TestRunner",
    "parse_pytest_summary",
    "CodingSessionSummary",
    "SessionSummaryBuilder",
    "parse_diff_numstat",
    "parse_status",
]
