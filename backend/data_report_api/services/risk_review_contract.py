"""Shared review encoding and validation for follow-up and workflow."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .risk_verification_flow import FlowError


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


def choice(value, options, label):
    if value not in options:
        raise FlowError(label + '无效')
    return value


def version(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlowError('请提供记录版本')
    return value
