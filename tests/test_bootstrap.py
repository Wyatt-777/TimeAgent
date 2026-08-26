from main import main


def test_bootstrap_entrypoint_returns_success() -> None:
    assert main(["--once"]) == 0
