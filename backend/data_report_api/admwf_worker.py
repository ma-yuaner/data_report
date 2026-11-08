"""Small isolated worker for the confirmed 48-hour recovery reminder state."""

import logging
import time

from .config import Config
from .services.admwf import AdmError
from .services.admwf.repository import AdmWorkflowRepository


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repository = AdmWorkflowRepository(vars(Config))
    interval = max(10, int(Config.ADM_RECOVERY_POLL_SECONDS))
    while True:
        try:
            count = repository.mark_due_recoveries()
            if count:
                logging.info("Marked %s ADM recovery reminders due", count)
        except AdmError as error:
            logging.error("ADM recovery reminder scan failed: %s", error.code)
        except Exception:
            logging.exception("ADM recovery reminder worker failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
