"""Periodic runner for the target-management incremental ETL."""
from __future__ import annotations

import logging
import os
import signal
import threading

from .target_management_daily import TargetManagementDailyJob, _config_dict


LOGGER = logging.getLogger(__name__)
STOP = threading.Event()


def _stop(_signum: int, _frame: object) -> None:
    STOP.set()


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    interval = max(60, int(os.getenv("TARGET_ETL_INTERVAL_SECONDS", "900")))
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    LOGGER.info("Target progress scheduler started; interval=%ss", interval)
    while not STOP.is_set():
        lock_connection = None
        try:
            job = TargetManagementDailyJob(_config_dict())
            lock_connection = job.acquire_run_lock()
            if lock_connection is None:
                LOGGER.info("Target progress ETL skipped; another run is active")
                STOP.wait(interval)
                continue
            results = job.run_incremental()
            LOGGER.info(
                "Target progress live ETL finished; dates=%s dws=%s ads=%s",
                len(results),
                sum(int(row["dwsRows"]) for row in results),
                sum(int(row["adsRows"]) for row in results),
            )
        except Exception:
            LOGGER.exception("Target progress incremental ETL failed; the next cycle will retry")
        finally:
            TargetManagementDailyJob.release_run_lock(lock_connection)
        STOP.wait(interval)
    LOGGER.info("Target progress scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
