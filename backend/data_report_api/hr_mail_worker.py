"""Dedicated durable mail worker. Never retry an uncertain external side effect."""
import logging
import signal
import time
from datetime import datetime

from .config import Config
from .services.auth import MySqlAuthStore
from .services.hr_mail.service import Service, now, permission
from .services.hr_mail.store import MailError, Store
from .services.hr_mail.transport import secret_config, sender, send_result
from .time_utils import business_now

LOGGER = logging.getLogger("hr-mail-worker")
STOP = False


def stop(_signal, _frame):
    global STOP
    STOP = True


def run_once(config):
    store = Store(config)
    for batch in store.active():
        if batch["status"] == "RUNNING":
            last = datetime.fromisoformat(batch["heartbeatAt"])
            if (business_now() - last).total_seconds() < 600:
                continue
            # No claim/automatic re-delivery after crash; in-flight may have sent.
            for item in batch["items"]:
                if item["status"] == "SENDING":
                    item.update(status="UNKNOWN", error="HR_MAIL_WORKER_INTERRUPTED：发送期间进程中断，请人工核实，未自动重发")
                elif item["status"] == "PENDING":
                    item.update(status="SKIPPED", error="批次中断，尚未发送")
            batch.update(status="INTERRUPTED", finishedAt=now())
            batch["events"].append({"action": "interrupted", "at": now()})
            try:
                store.save(batch, batch["version"])
            except MailError as error:
                if error.code != "HR_MAIL_CONFLICT":
                    raise
            continue
        try:
            batch.update(status="RUNNING", heartbeatAt=now(), startedAt=now())
            batch = store.save(batch, batch["version"])
        except MailError as error:
            if error.code == "HR_MAIL_CONFLICT":
                continue
            raise
        mailer = None
        try:
            if not config.get("HR_MAIL_SEND_ENABLED", False):
                raise MailError("发送开关已关闭", "HR_MAIL_SEND_DISABLED")
            secret_config(config)
            # Revalidate the confirming account, not a front-end user snapshot.
            resolver = config.get("HR_MAIL_TEST_USER_RESOLVER") if config.get("TESTING") else None
            user = resolver(int(batch["confirmedBy"])) if resolver else MySqlAuthStore(config).get_user_by_id(int(batch["confirmedBy"]))
            permission(user, "send")
            service = Service(config, user)
            factory = config.get("HR_MAIL_TEST_SENDER") if config.get("TESTING") else None
            mailer = factory() if factory else sender(config)
            for index in range(len(batch["items"])):
                item = batch["items"][index]
                if item["status"] != "PENDING":
                    continue
                if STOP:
                    raise MailError("进程停止，后续未发送", "HR_MAIL_WORKER_STOPPING")
                path, _ = service.file(batch["id"], item["attachment"]["url"].rsplit("/", 1)[-1])
                if service.frozen_hash(item) != item["frozenHash"] or not item["valid"] or not item["to"].strip():
                    raise MailError("冻结邮件或收件信息无效", "HR_MAIL_CONTENT_CHANGED")
                item.update(status="SENDING", startedAt=now())
                batch["heartbeatAt"] = now()
                batch["events"].append({"action": "sending", "itemId": item["id"], "at": now()})
                batch = store.save(batch, batch["version"])
                item = batch["items"][index]
                status, error = send_result(mailer, item, path)
                item.update(status=status, error=error, finishedAt=now())
                batch["heartbeatAt"] = now()
                batch["events"].append({"action": status.lower(), "itemId": item["id"], "at": now(), "error": error})
                batch = store.save(batch, batch["version"])
            batch.update(status="COMPLETED", finishedAt=now())
            store.save(batch, batch["version"])
        except Exception as error:
            # Read durable state: if the previous commit was uncertain, do not
            # overwrite a newer state or misreport an external send as unsent.
            fresh = store.get(batch["id"])
            if fresh["status"] != "RUNNING":
                continue
            code = error.code if isinstance(error, MailError) else "HR_MAIL_WORKER_ERROR"
            for item in fresh["items"]:
                if item["status"] == "SENDING":
                    item.update(status="UNKNOWN", error=code + "：发送结果未知，请核实，未自动重发")
                elif item["status"] == "PENDING":
                    item.update(status="FAILED", error=code + "：未开始发送，请核对配置、权限或附件")
            fresh.update(status="INTERRUPTED", finishedAt=now())
            fresh["events"].append({"action": "interrupted", "at": now(), "error": code})
            store.save(fresh, fresh["version"])
        finally:
            if mailer:
                mailer.close()
        return True
    return False


def main():
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    config = {key: getattr(Config, key) for key in dir(Config) if key.isupper()}
    while not STOP:
        try:
            run_once(config)
        except Exception:
            LOGGER.error("HR_MAIL_WORKER_UNAVAILABLE: check database/DDL/Secret; no automatic mail retry")
        for _ in range(5):
            if STOP:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
