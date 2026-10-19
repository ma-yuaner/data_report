# GDS资源指标服务表数据契约

- 更新日期：2026-10-16
- 页面读取表：`sibebid.bi_gds_resource_metric_day`
- 上游请求表：`sibebid.bi_ota_gds_request_day`
- 上游航段表：`sibebid.bi_issue_segment_pnr_year`
- 当前分工：数据团队负责建表和ETL，数据中台负责API、页面和后续规则消费

## 1. 为什么需要服务表

请求表按`source_api_group`拆分，航段表没有该维度。如果把两张表直接按明细行关联，`1A`、`1A_NDC`、`1A_MPIS`会重复连接同一份航段数，导致查定比错误。

服务表必须同时产出两类互斥记录：

| `metric_scope` | 用途 | `source_api_group` | 是否允许有`seg_num` |
|---|---|---|---|
| `MP_TOTAL` | 正式MP查询量、航段数和查定比 | 固定`MP_TOTAL` | 是 |
| `API_GROUP` | 各接口组查询、验价、生单的成功/失败分析 | 原始接口组，如`1A_NDC` | 否，必须为NULL |

## 2. 正式口径

```text
MP查询量 = SUM(search_request_count_all)，其中source_api_group不以_MPIS结尾
GDS查定比 = MP查询量 / SUM(seg_num)
```

- `1A`、`1A_NDC`计入MP查询量；`1A_MPIS`不计入；1G等其他GDS使用相同规则。
- 页面分析层级固定为`GDS → 资源通道 → 接口分组`。资源通道按接口组名称派生：以`_MPIS`结尾为`MPIS`，其余为`MP`；因此`1A_NDC`是MP的下级接口组，不与MP平级。
- `MPIS查询占比 = MPIS查询量 / (MP查询量 + MPIS查询量)`，只用于观察流量迁移，不替代正式查定比。
- 分母固定来自`bi_issue_segment_pnr_year.seg_num`，只汇总`flag=1`的出票航段；历史`flag IS NULL`按出票兼容，`flag=0`订位航段排除。
- `pnr_num`、`iss_num`、`order_num`和接口`order_request_success`不作为查定比分母。
- 同一完整业务日内，某个细分组合没有航段记录表示该组合航段数为0，不是“未同步”。
- 只有整个业务日都没有航段源数据时，才保留NULL并将`segment_missing_flag=1`。
- 查询量大于0且已确认航段数为0时，页面显示无穷大；数据未同步时显示“—”。

## 3. 必须字段

```sql
CREATE TABLE sibebid.bi_gds_resource_metric_day (
    operator_date DATE NOT NULL COMMENT '业务日期',
    metric_scope VARCHAR(20) NOT NULL COMMENT 'MP_TOTAL或API_GROUP',
    ota_code VARCHAR(50) NOT NULL DEFAULT '' COMMENT '平台编码',
    ota_cname VARCHAR(100) NOT NULL DEFAULT '' COMMENT '平台名称',
    ota_site_code VARCHAR(50) NOT NULL DEFAULT '' COMMENT '站点编码',
    ota_site_cname VARCHAR(100) NOT NULL DEFAULT '' COMMENT '站点名称',
    gds_code VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'GDS编码，如1A或1G',
    pcc_code VARCHAR(100) NOT NULL DEFAULT '' COMMENT 'PCC编码',
    source_api_group VARCHAR(100) NOT NULL COMMENT 'MP_TOTAL或原始接口分组',
    search_request_count_all BIGINT NOT NULL DEFAULT 0,
    search_request_success BIGINT NOT NULL DEFAULT 0,
    verify_request_count_all BIGINT NOT NULL DEFAULT 0,
    verify_request_success BIGINT NOT NULL DEFAULT 0,
    order_request_count_all BIGINT NOT NULL DEFAULT 0,
    order_request_success BIGINT NOT NULL DEFAULT 0,
    search_cache_count BIGINT NOT NULL DEFAULT 0,
    verify_cache_count BIGINT NOT NULL DEFAULT 0,
    order_cache_count BIGINT NOT NULL DEFAULT 0,
    search_execute_time BIGINT NOT NULL DEFAULT 0 COMMENT '查询总耗时',
    verify_execute_time BIGINT NOT NULL DEFAULT 0 COMMENT '验价总耗时',
    order_execute_time BIGINT NOT NULL DEFAULT 0 COMMENT '生单总耗时',
    search_price_change_count BIGINT NOT NULL DEFAULT 0,
    verify_price_change_count BIGINT NOT NULL DEFAULT 0,
    order_price_change_count BIGINT NOT NULL DEFAULT 0,
    seg_num BIGINT NULL COMMENT '仅MP_TOTAL有值',
    segment_missing_flag TINYINT NOT NULL DEFAULT 0 COMMENT 'MP_TOTAL航段是否缺失',
    pnr_num BIGINT NULL COMMENT '辅助指标，不参与正式查定比',
    iss_num BIGINT NULL COMMENT '辅助指标',
    order_num BIGINT NULL COMMENT '辅助指标',
    request_updated_at DATETIME NULL COMMENT '请求事实最新同步时间',
    segment_updated_at DATETIME NULL COMMENT '航段事实最新同步时间',
    etl_updated_at DATETIME NOT NULL COMMENT '服务表清洗完成时间',
    PRIMARY KEY (
        operator_date, metric_scope, ota_code, ota_site_code,
        gds_code, pcc_code, source_api_group
    ),
    KEY idx_gds_date (gds_code, operator_date),
    KEY idx_scope_date (metric_scope, operator_date),
    KEY idx_platform_date (ota_code, operator_date),
    KEY idx_pcc_date (pcc_code, operator_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='GDS资源治理页面与规则统一指标服务表';
```

如现网MySQL版本不支持超长联合主键，可改用自增`id`主键，并为上述业务键建立唯一索引；业务唯一性不能取消。

## 4. ETL产出规则

1. 只读取`bi_ota_gds_request_day.data_source=1`的GDS记录。
2. `API_GROUP`按日期、平台、站点、GDS、PCC、原始接口组汇总全部接口基础量，`seg_num=NULL`。
3. `MP_TOTAL`在同样业务维度下过滤掉`source_api_group LIKE '%_MPIS'`后汇总请求基础量。
4. 航段表先独立按日期、平台、站点、GDS、PCC汇总，再与`MP_TOTAL`一对一关联。
5. 两个上游的空维度统一为相同空串后再关联，不能一边NULL、一边空串。
6. 日表只处理截至昨日的完整业务日；今天的数据未来由小时表提供。
7. 默认清洗区间取两张源表的重叠日期，并且结束日期不晚于昨日。
8. 航段表当日存在数据时，细分键未关联到航段的`seg_num`写0，`segment_missing_flag=0`。
9. 每次ETL必须覆盖完整业务日；不要对累计表重复追加同一天。
10. 同一天同一业务键只能有一行，重跑结果必须幂等。

## 5. 页面字段来源

| 页面功能 | 数据记录 |
|---|---|
| MP查询量、航段数、查定比、超额查询 | `metric_scope='MP_TOTAL'` |
| GDS/PCC/平台/站点对比与日趋势 | `metric_scope='MP_TOTAL'` |
| MP与MPIS查询量及占比 | `MP_TOTAL`汇总MP，`API_GROUP`汇总`*_MPIS` |
| 普通MP、NDC、MPIS等接口分组质量 | `metric_scope='API_GROUP'`，在所属资源通道下展示 |
| 查询/验价/生单失败量 | 页面使用`请求量-成功量`实时计算 |
| 接口组“分析此项” | `API_GROUP`继续按GDS、PCC、平台、站点下钻 |

## 6. 后续规则衔接

后续GDS查定比异常规则必须读取`MP_TOTAL`，接口成功率异常规则读取`API_GROUP`。规则命中后继续复用现有异常事件、负责人、技术工单和上下线回执流程，不再从旧请求表临时拼航段分母。

## 7. 与原1A监控日报的覆盖关系

现有`gds_1a_search_rate_monitor.py`不只是查定比日报，还包含MPIS规则和高基数问题诊断。新架构分层覆盖，不能把所有字段堆进主服务表：

| 原报告能力 | 当前服务表/页面 | 后续接入方式 |
|---|---|---|
| 日/月查询量、航段数、航段查定比、趋势 | 已覆盖 | `MP_TOTAL` |
| GDS、PCC、平台、站点、API组对比 | 已覆盖 | 服务表连续下钻 |
| 查询、验价、生单成功/失败及成功率 | 已覆盖 | `API_GROUP`与页面基础量重算 |
| PNR数、PNR辅助查定比 | 表已预留`pnr_num`，页面暂未展示 | 作为辅助指标接入，不替代正式航段查定比 |
| MPIS规则命中率、MPIS占比、MPIS失败率 | 当前两张上游表不能完整提供 | 复用`dws_gds_mpis_interval_rate_all`形成独立MPIS质量日表 |
| 配置规则命中明细、PCC+航线命中 | 当前两张上游表不能提供 | 复用`bi_gds_mpis_interval_rate_day`作为诊断页来源 |
| 失败原因TOP | 当前服务表不存错误明细 | 从5分钟DWD汇总独立的失败原因日表，命中后按短日期下钻 |
| 去程/回程间隔、人数、航线覆盖 | 当前服务表不存高基数维度 | 从`dws_gds_interval_day`或短周期Hive明细按需查询 |
| HTML邮件、Excel附件 | 数据中台页面已替代HTML正文 | 后续由统一导出模板和通知中心生成，避免脚本硬编码收件人 |

因此，当前V1已经覆盖老板日常查看的主指标和第一层问题定位；要完全替代旧邮件附件，还需新增“MPIS质量”和“问题诊断”两个下钻数据集，但不需要推翻当前表与页面。
