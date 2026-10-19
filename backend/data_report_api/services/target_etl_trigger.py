"""Asynchronous manual trigger and status service for target-management ETL."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from ..target_management_daily import TargetManagementDailyJob
from ..time_utils import business_now
from .data_source import DataSource
from .target_management import MANAGE_PERMISSION, PROGRESS_PERMISSION, VIEW_PERMISSION, _permissions


LOGGER = logging.getLogger(__name__)
ACTIVE_STATUSES = frozenset({"QUEUED", "RUNNING"})
REQUEST_LOCK_NAME = "datareport_target_management_etl_request"


class TargetEtlTriggerUnavailable(RuntimeError):
    pass


class TargetEtlTriggerConflict(RuntimeError):
    pass


def _require_any(user: dict[str, Any], allowed: set[str], message: str) -> None:
    if user.get("is_admin") or user.get("isAdmin") or (_permissions(user) & allowed):
        return
    raise PermissionError(message)


def _config_dict(config: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in config.items() if str(key).isupper()}


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


class TargetEtlTriggerService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        mysql_config = dict(config)
        mysql_config["DATA_MODE"] = "mysql"
        self.config = _config_dict(mysql_config)
        self.source = source or DataSource(mysql_config)
        self.database = self.source.database
        self.cooldown_seconds = max(0, int(config.get("TARGET_ETL_MANUAL_COOLDOWN_SECONDS", 120)))
        self.lock_wait_seconds = max(0, int(config.get("TARGET_ETL_MANUAL_LOCK_WAIT_SECONDS", 30)))
        self.stale_seconds = max(300, int(config.get("TARGET_ETL_MANUAL_STALE_SECONDS", 7200)))

    @property
    def _runs(self) -> str:
        return f"{self.database}.target_etl_run"

    @staticmethod
    def _public(row: dict[str, Any] | None, *, cooldown_seconds: int = 0) -> dict[str, Any]:
        if not row:
            return {
                "id": None, "status": "IDLE", "triggerType": None, "requestedBy": "",
                "requestedAt": None, "startedAt": None, "finishedAt": None,
                "dataThroughDate": None, "processedDates": 0, "dwsRows": 0, "adsRows": 0,
                "errorMessage": "", "canTrigger": True, "retryAfterSeconds": 0,
            }
        status = str(row.get("status") or "IDLE")
        return {
            "id": int(row["id"]),
            "status": status,
            "triggerType": str(row.get("trigger_type") or "MANUAL"),
            "requestedBy": str(row.get("requested_by_name") or ""),
            "requestedAt": _iso(row.get("requested_at")),
            "startedAt": _iso(row.get("started_at")),
            "finishedAt": _iso(row.get("finished_at")),
            "dataThroughDate": _iso(row.get("data_through_date")),
            "processedDates": int(row.get("processed_dates") or 0),
            "dwsRows": int(row.get("dws_rows") or 0),
            "adsRows": int(row.get("ads_rows") or 0),
            "errorMessage": str(row.get("error_message") or ""),
            "canTrigger": status not in ACTIVE_STATUSES and cooldown_seconds <= 0,
            "retryAfterSeconds": max(0, int(cooldown_seconds)),
        }

    def _latest(self, cursor: Any) -> dict[str, Any] | None:
        cursor.execute(f"""SELECT * FROM {self._runs} ORDER BY id DESC LIMIT 1""")
        row = cursor.fetchone()
        latest = dict(row) if row else None
        if (
            latest and str(latest.get("status")) in ACTIVE_STATUSES
            and isinstance(latest.get("requested_at"), datetime)
            and latest["requested_at"] < business_now().replace(tzinfo=None) - timedelta(seconds=self.stale_seconds)
        ):
            cursor.execute(
                f"""UPDATE {self._runs}
                    SET status='FAILED',finished_at=CURRENT_TIMESTAMP,
                        error_message='任务进程中断或运行超时，请重新触发'
                    WHERE id=%s AND status IN ('QUEUED','RUNNING')""",
                (latest["id"],),
            )
            latest.update({
                "status": "FAILED", "finished_at": business_now().replace(tzinfo=None),
                "error_message": "任务进程中断或运行超时，请重新触发",
            })
        return latest

    def _cooldown(self, row: dict[str, Any] | None) -> int:
        if not row or not row.get("requested_at") or str(row.get("status")) in ACTIVE_STATUSES:
            return 0
        requested_at = row["requested_at"]
        if not isinstance(requested_at, datetime):
            return 0
        elapsed = int((business_now().replace(tzinfo=None) - requested_at).total_seconds())
        return max(0, self.cooldown_seconds - elapsed)

    def status(self, user: dict[str, Any]) -> dict[str, Any]:
        _require_any(
            user, {VIEW_PERMISSION, PROGRESS_PERMISSION, MANAGE_PERMISSION},
            "当前账号没有目标进度查看权限",
        )
        import pymysql

        connection = None
        try:
            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                latest = self._latest(cursor)
            return self._public(latest, cooldown_seconds=self._cooldown(latest))
        except PermissionError:
            raise
        except Exception as error:
            LOGGER.exception("Target ETL trigger status query failed")
            raise TargetEtlTriggerUnavailable("立即更新状态不可用，请确认运行记录表已部署") from error
        finally:
            if connection is not None:
                connection.close()

    def trigger(self, user: dict[str, Any]) -> dict[str, Any]:
        _require_any(user, {MANAGE_PERMISSION}, "当前账号没有立即更新目标进度的权限")
        import pymysql

        connection = None
        request_lock_acquired = False
        try:
            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT GET_LOCK(%s, 3) AS acquired", (REQUEST_LOCK_NAME,))
                request_lock_acquired = bool((cursor.fetchone() or {}).get("acquired"))
                if not request_lock_acquired:
                    raise TargetEtlTriggerConflict("立即更新请求较多，请稍后重试")
                latest = self._latest(cursor)
                if latest and str(latest.get("status")) in ACTIVE_STATUSES:
                    raise TargetEtlTriggerConflict("目标进度正在更新，请勿重复触发")
                retry_after = self._cooldown(latest)
                if retry_after > 0:
                    raise TargetEtlTriggerConflict(f"请等待 {retry_after} 秒后再次更新")
                actor_id = int(user.get("id") or 0) or None
                actor_name = str(
                    user.get("display_name") or user.get("displayName")
                    or user.get("username") or user.get("user_name") or ""
                ).strip()[:100]
                cursor.execute(
                    f"""INSERT INTO {self._runs}
                        (trigger_type,status,requested_by_user_id,requested_by_name,data_through_date)
                        VALUES ('MANUAL','QUEUED',%s,%s,%s)""",
                    (actor_id, actor_name, business_now().date()),
                )
                run_id = int(cursor.lastrowid)
                cursor.execute(f"SELECT * FROM {self._runs} WHERE id=%s", (run_id,))
                created = dict(cursor.fetchone())
            threading.Thread(
                target=self._execute,
                args=(run_id,),
                name=f"target-etl-manual-{run_id}",
                daemon=True,
            ).start()
            return self._public(created)
        except (PermissionError, TargetEtlTriggerConflict):
            raise
        except Exception as error:
            LOGGER.exception("Target ETL trigger request failed")
            raise TargetEtlTriggerUnavailable("立即更新提交失败，请确认运行记录表和数据库连接可用") from error
        finally:
            if connection is not None:
                if request_lock_acquired:
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT RELEASE_LOCK(%s)", (REQUEST_LOCK_NAME,))
                    except Exception:
                        LOGGER.warning("Failed to release target ETL request lock", exc_info=True)
                connection.close()

    def _update_run(self, run_id: int, sql: str, params: tuple[Any, ...] = ()) -> None:
        connection = self.source.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE {self._runs} SET {sql} WHERE id=%s", (*params, run_id))
        finally:
            connection.close()

    def _execute(self, run_id: int) -> None:
        lock_connection = None
        try:
            job = TargetManagementDailyJob(self.config)
            lock_connection = job.acquire_run_lock(self.lock_wait_seconds)
            if lock_connection is None:
                raise RuntimeError("已有自动或手动目标ETL正在运行，请稍后再次更新")
            self._update_run(run_id, "status='RUNNING',started_at=CURRENT_TIMESTAMP,error_message=NULL")
            results = job.run_incremental()
            self._update_run(
                run_id,
                "status='SUCCEEDED',finished_at=CURRENT_TIMESTAMP,processed_dates=%s,dws_rows=%s,ads_rows=%s",
                (
                    len(results),
                    sum(int(row["dwsRows"]) for row in results),
                    sum(int(row["adsRows"]) for row in results),
                ),
            )
            LOGGER.info("Manual target ETL finished; run_id=%s dates=%s", run_id, len(results))
        except Exception as error:
            LOGGER.exception("Manual target ETL failed; run_id=%s", run_id)
            try:
                self._update_run(
                    run_id,
                    "status='FAILED',finished_at=CURRENT_TIMESTAMP,error_message=%s",
                    (str(error)[:1000],),
                )
            except Exception:
                LOGGER.exception("Failed to persist manual target ETL error; run_id=%s", run_id)
        finally:
            TargetManagementDailyJob.release_run_lock(lock_connection)
