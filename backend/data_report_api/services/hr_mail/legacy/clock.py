"""Keep desktop footer wall time in the platform's explicit business timezone."""
from datetime import datetime as BaseDateTime
from ....time_utils import ASIA_SHANGHAI


class datetime(BaseDateTime):
    @classmethod
    def now(cls, tz=None):
        value = BaseDateTime.now(tz or ASIA_SHANGHAI)
        return value if tz else value.replace(tzinfo=None)
