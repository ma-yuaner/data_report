"""Run explicitly: python -m data_report_api.adm_worker [--once]. No production DDL."""
import argparse
import logging
import signal
import threading

from .config import Config
from .services.adm import AdmService
from .services.adm.attachments import verify_stored_attachment
from .services.adm.notifications import NotificationWorker
from .services.adm.providers import configure_providers
from .services.auth import AuthManager, MySqlAuthStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = {key: getattr(Config, key) for key in dir(Config) if key.isupper()}
    manager = AuthManager(MySqlAuthStore(config), config)
    configure_providers(config, manager)
    config["ADM_ATTACHMENT_VERIFIER"] = lambda item: verify_stored_attachment(config, item)
    worker = NotificationWorker(AdmService(config))
    stopped = threading.Event()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            result = worker.run_once()
            logging.info("ADM worker enabled=%s created=%s", result.get("enabled"), result.get("created", 0))
        except Exception:
            # No raw URLs, credentials, employee identifiers or driver exception dumps in logs.
            logging.error("ADM worker cycle failed; inspect configured schema, approval and sanitized delivery ledger")
        if args.once:
            break
        stopped.wait(30)


if __name__ == "__main__":
    main()
