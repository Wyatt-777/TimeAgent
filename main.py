"""Local PC Agent application entry point."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence

from config import load_settings
from core.lifecycle import Runtime, configure_logging


def main(argv: Sequence[str] | None = None) -> int:
    """Start the runtime until Ctrl+C, or run one start/stop smoke cycle."""
    parser = argparse.ArgumentParser(description="Run the Local PC Agent runtime")
    parser.add_argument(
        "--once",
        action="store_true",
        help="start and stop once, useful for installation and health checks",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(settings)
    runtime = Runtime(settings)
    runtime.start()
    try:
        if args.once:
            return 0
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
