"""Read-only cabin hints for new opportunities. Never supplies matching/task fields."""
import logging
import re

from .data_source import DataSource
from .smart_placement import SmartPlacementUnavailable, PERMISSION_CREATE, _actor, _require_permission
from ..time_utils import business_now_naive

LOGGER = logging.getLogger(__name__)
MAX_DISTINCT_VALUES = 2000


class PlacementCabinReferenceService:
    def __init__(self, config, *, source=None):
        erp = {**config, 'DATA_MODE': 'mysql', 'MYSQL_DATABASE': 'sibebd'}
        for key in ('HOST', 'PORT', 'USER', 'PASSWORD', 'CHARSET', 'CONNECT_TIMEOUT', 'READ_TIMEOUT', 'WRITE_TIMEOUT', 'POOL_SIZE', 'POOL_MIN_CACHED'):
            if config.get(f'ERP_MYSQL_{key}') not in (None, ''):
                erp[f'MYSQL_{key}'] = config[f'ERP_MYSQL_{key}']
        self.source = source or DataSource(erp)

    def get(self, user, airline):
        _actor(user)
        if not (user.get('is_admin') or user.get('isAdmin') or 'smart.placement.policies' in (user.get('menu_codes') or user.get('menuCodes') or [])):
            raise PermissionError('当前账号没有投放政策菜单权限')
        _require_permission(user, PERMISSION_CREATE, '当前账号没有新建分析机会权限')
        code = str(airline or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{2}', code):
            raise ValueError('请选择有效的两位航司代码')
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"""SELECT DISTINCT cabin FROM `sibebd`.`hold_info_flight_list`
                WHERE status=1 AND airline=%s AND update_time>=DATE_SUB(%s, INTERVAL 1 MONTH)
                AND update_time<=%s LIMIT {MAX_DISTINCT_VALUES + 1}""", (code, current, current))
            rows = list(cursor.fetchall())
            if len(rows) > MAX_DISTINCT_VALUES:
                raise SmartPlacementUnavailable('参考舱位配置较多，暂不展示，请核对ERP配置')
            cabins = set()
            unspecified = False
            for row in rows:
                raw = row.get('cabin') if isinstance(row, dict) else row[0]
                values = [value.strip().upper() for value in str(raw or '').split('|') if value.strip()]
                if not values:
                    unspecified = True
                cabins.update(values)
            return {'airline': code, 'cabins': sorted(cabins), 'hasUnspecified': unspecified}
        except SmartPlacementUnavailable:
            raise
        except Exception as error:
            LOGGER.exception('Placement cabin reference lookup failed')
            raise SmartPlacementUnavailable('参考舱位暂不可用，请核对ERP sibebd.hold_info_flight_list读取权限') from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
