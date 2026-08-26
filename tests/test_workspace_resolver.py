from pathlib import Path

from workspace.resolver import WorkspaceResolver


def test_resolver_matches_most_specific_configured_workspace(tmp_path: Path) -> None:
    root = tmp_path / "project"
    nested = root / "packages" / "app"
    resolver = WorkspaceResolver([root, nested])

    match = resolver.resolve(nested / "src" / "main.py")

    assert match is not None
    assert match.workspace.path == nested.resolve()
    assert match.relative_path == Path("src") / "main.py"


def test_resolver_does_not_guess_unconfigured_paths(tmp_path: Path) -> None:
    resolver = WorkspaceResolver([tmp_path / "project"])

    assert resolver.resolve(tmp_path / "other" / "main.py") is None
    assert resolver.resolve(None) is None
