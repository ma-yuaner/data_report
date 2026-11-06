"""Transactional sibebid storage for automatic risk checks; never creates tables."""
from contextlib import contextmanager
import re
import sys

from .data_source import DataSource


class StoreConflict(Exception):
    """A unique key or other integrity constraint rejected a write."""


class StoreUnavailable(RuntimeError):
    """Safe infrastructure error suitable for a 503 response."""


class StoreCommittedCleanupError(StoreUnavailable):
    """Commit was acknowledged; only resource finalization failed."""
    committed = True


UNAVAILABLE = "风控MySQL存储未就绪，请检查sibebid新表及读写权限"


def _operation(function, *args):
    from pymysql.err import IntegrityError
    try:
        return function(*args)
    except IntegrityError as error:
        raise StoreConflict("Automatic risk storage integrity conflict") from error
    except (StoreConflict, StoreUnavailable):
        raise
    except Exception as error:
        raise StoreUnavailable(UNAVAILABLE) from error


COLUMNS = {
    "auto_jobs": ("id", "owner", "status", "updated", "body"),
    "auto_results": ("id", "owner", "order_id", "created", "body"),
    "auto_samples": ("id", "owner", "result_id", "body"),
}


def mysql_sql(sql):
    """Translate only the service's fixed SQL vocabulary, never user input."""
    for table, columns in COLUMNS.items():
        sql = re.sub(rf"\bINSERT\s+INTO\s+{table}\s+VALUES\b",
                     f"INSERT INTO {table} ({','.join(columns)}) VALUES", sql, flags=re.I)
        sql = re.sub(rf"\b{table}\b", f"bi_risk_{table}", sql, flags=re.I)
    return re.sub(r"\browid\b", "seq", sql, flags=re.I).replace("?", "%s")


class _Result:
    def __init__(self, cursor=None):
        self.cursor = cursor
        self.rowcount = 0 if cursor is None else cursor.rowcount

    def _row(self, row):
        if row is None or isinstance(row, dict):
            return row
        return dict(zip((item[0] for item in self.cursor.description), row))

    def fetchone(self):
        return self._row(_operation(self.cursor.fetchone))

    def fetchall(self):
        return [self._row(row) for row in _operation(self.cursor.fetchall)]

    def __iter__(self):
        return iter(self.fetchall())


class _Session:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=()):
        if sql.strip().rstrip(";").upper() == "BEGIN IMMEDIATE":
            return _Result()
        _operation(self.cursor.execute, mysql_sql(sql), params)
        return _Result(self.cursor)

    def executemany(self, sql, rows):
        _operation(self.cursor.executemany, mysql_sql(sql), rows)
        return _Result(self.cursor)


class RiskAutoStore:
    def __init__(self, config, source=None):
        if str(config.get("MYSQL_DATABASE", "sibebid")).strip() != "sibebid":
            raise StoreUnavailable(UNAVAILABLE)
        values = dict(config)
        values["DATA_MODE"] = "mysql"
        for key in ("CONNECT_TIMEOUT", "READ_TIMEOUT", "WRITE_TIMEOUT"):
            values[f"MYSQL_{key}"] = min(max(int(values.get(f"MYSQL_{key}", 8)), 1), 8)
        self.source = source if source is not None else DataSource(values)
        if getattr(self.source, "mode", "mysql") != "mysql" or getattr(self.source, "database", "sibebid") != "sibebid":
            raise StoreUnavailable(UNAVAILABLE)

    @contextmanager
    def db(self, consistent_snapshot=False):
        connection = _operation(self.source.connect)
        cursor = None
        committed = False
        try:
            # DataSource's pooled connections default to autocommit=True.
            if consistent_snapshot:
                cursor = _operation(connection.cursor)
                _operation(cursor.execute, 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                _operation(cursor.execute, 'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            else:
                _operation(connection.begin)
                cursor = _operation(connection.cursor)
            yield _Session(cursor)
            _operation(connection.commit)
            committed = True
        except BaseException:
            try:
                connection.rollback()
            except Exception:
                pass  # Preserve the original failure; never commit after it.
            raise
        finally:
            original_failure = sys.exc_info()[0] is not None
            close_error = None
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception as error:
                        close_error = error
            if close_error is not None and not original_failure:
                if committed:
                    raise StoreCommittedCleanupError(UNAVAILABLE) from close_error
                raise StoreUnavailable(UNAVAILABLE) from close_error
