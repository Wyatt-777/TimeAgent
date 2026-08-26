"""Run a long-lived runtime soak test and write a local measurement log."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from config import load_settings
from core.lifecycle import Runtime, configure_logging


def run(duration_hours: float = 8.0, interval_seconds: float = 60.0) -> Path:
    if duration_hours <= 0:
        raise ValueError("duration_hours must be greater than zero")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")

    settings = load_settings()
    configure_logging(settings)
    log_dir = Path(settings.storage.log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    log_path = log_dir / f"stability-{started_at.strftime('%Y%m%dT%H%M%SZ')}.log"
    process = psutil.Process()
    runtime = Runtime(settings)
    deadline = time.monotonic() + duration_hours * 3600

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"started_at={started_at.isoformat()}\n")
        log.write(f"duration_hours={duration_hours}\n")
        log.write(f"interval_seconds={interval_seconds}\n")
        process.cpu_percent(None)
        runtime.start()
        try:
            while time.monotonic() < deadline:
                time.sleep(min(interval_seconds, max(0.0, deadline - time.monotonic())))
                log.write(
                    "sample "
                    f"timestamp={datetime.now(timezone.utc).isoformat()} "
                    f"events={runtime.event_store.count()} "
                    f"cpu_percent={process.cpu_percent(None):.2f} "
                    f"memory_mb={process.memory_info().rss / 1024 / 1024:.2f}\n"
                )
                log.flush()
        except Exception as exc:
            log.write(f"error={type(exc).__name__}: {exc}\n")
            raise
        finally:
            runtime.shutdown(timeout=10)
            log.write(f"ended_at={datetime.now(timezone.utc).isoformat()}\n")
    return log_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Local PC Agent stability test")
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    args = parser.parse_args()
    log_path = run(args.hours, args.interval_seconds)
    print(f"Stability log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
