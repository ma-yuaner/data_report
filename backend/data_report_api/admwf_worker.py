"""Small isolated worker for the confirmed 48-hour recovery reminder state."""

import logging
import time

from .config import Config
from .services.admwf import AdmError
from .services.admwf.repository import AdmWorkflowRepository
from .services.admwf.operations import AdmOperations


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repository = AdmWorkflowRepository(vars(Config))
    operations = AdmOperations(vars(Config), repository=repository)
    interval = max(10, int(Config.ADM_RECOVERY_POLL_SECONDS))
    while True:
        try:
            count = repository.mark_due_recoveries() + repository.advance_master_recovery()
            repository.mark_overdue_assignments()
            if count:
                logging.info("Marked %s ADM recovery reminders due", count)
        except AdmError as error:
            logging.error("ADM recovery reminder scan failed: %s", error.code)
        except Exception:
            logging.exception("ADM recovery reminder worker failed")
        try:
            sent = operations.send_due()
            if sent:
                logging.info("Sent %s ADM digest messages", sent)
        except Exception as error:
            logging.error("ADM digest scan failed: %s", getattr(error, "code", type(error).__name__))
        time.sleep(interval)


if __name__ == "__main__":
    main()
