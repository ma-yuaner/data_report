"""Compatibility entry for the target-management job."""
from .jobs.target_management import (
    Scope,
    TargetManagementDailyJob,
    main,
    source_daily_sql,
    weekday_progress_rate,
)

__all__ = ['Scope', 'TargetManagementDailyJob', 'main', 'source_daily_sql', 'weekday_progress_rate']

if __name__ == "__main__":
    raise SystemExit(main())
