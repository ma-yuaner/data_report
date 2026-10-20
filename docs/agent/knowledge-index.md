# 知识与证据索引

核对日期：2026-10-20。当前“外挂知识库”是可追溯资料索引与Git文档，不是已上线的向量库。原始数据不复制进提示词。

| 主题 | 权威入口/证据 | 状态和边界 |
|---|---|---|
| 公司机票知识 | [业务目录](../business/air_ticketing/README.md)、`sources/2026-09-11-meeting.md` | 会议部分仍待确认；不代表所有新模块口径都未确认 |
| 销售报表平台替换 | [开发交接](workstreams.md#销售报表上海妤芯替换开发2026-10-20)、[真实验收交接](workstreams.md#明鉴v2与销售报表真实测试2026-10-20)、SALES-001/002；ETL仓库`docs/development/README.md`，验收脚本`analysis/tests/verify_business_sales_delivery.py`仅本地忽略保留、不随Git交付 | CX单列、UNIFIFI归其他；两张主报表已真实ERP只读汇总核对并发测试群，副本仅离线验证；未部署、未写快照、未发业务群。原始数据/图片不入Git，计时和回执留在忽略目录 |
| GDS本轮方案 | [业务闭环复评V3](../product/gds-resource-governance-reassessment-v3.md) | 人工闭环与首个分析课题已确认；细项待继续审核 |
| 平台站点航线双零异常 | [数据静态评估与首版清单V1](../product/gds-route-anomaly-data-readiness-v1.md) | 小时源有条件可复用，日聚合丢平台/站点，分钟DDL与产出不一致，查询机场为空；3/7候选仅完成合成场景推演，真实回测和正式参数未确认 |
| 历史需求和表接口 | [PRD V2](../product/gds-resource-governance-prd-v2.md) | 历史实现基线，新增提议不视作已开发 |
| 服务表口径 | [数据契约](../business/air_ticketing/gds-resource-metric-table-contract.md) | 结合实际源结构及本轮完整性风险读取 |
| 页面/API现状 | [实现说明](../business/air_ticketing/gds-resource-governance-live.md)、`backend/data_report_api/services/resource_governance.py` | 已检查代码，未连接生产重新验数 |
| Hive航线 | `backend/data_report_api/services/gds_route_analysis.py`、[验证SQL](../sql/gds-route-analysis-validation.sql) | 三阶段指标；Top500；无航段分母及错误原因 |
| 演示边界 | [航线治理页面说明](../business/air_ticketing/gds-route-governance-preview.md)、`frontend/src/stores/gdsRouteGovernance.ts` | 配置/白名单/执行/复盘有假数据，localStorage不落库 |
| 规则、事件、工单 | `backend/data_report_api/services/monitoring.py`、[操作说明](../business/air_ticketing/gds-resource-governance-operation-guide.md) | 当前资源模板为GDS日查定比、OTA日成功率；不能推断任意规则均支持 |
| 请求/航段清洗 | 独立ETL仓库`etl_scripts/automation/bi_gds_resource_metric_day_etl.py` | 已检查干净检出目录代码；保存两源键并集，航段先聚合后关联 |
| 日检查/生命周期/发送 | ETL仓库`etl_scripts/automation/monitoring/monitor_resource_governance_daily.py`、`monitor_resource_event_lifecycle.py`、`monitor_notification_dispatcher.py` | 代码存在；实际调度与发送结果需运行证据 |
| 旧1A日报 | ETL仓库`analysis/scripts/work/send_wechat/gds_1a_search_rate_monitor.py` | 仅作数据源与旧分析能力参考；其中旧阈值和口径不覆盖新确认决策 |
| 部署SQL | `docs/sql/resource-governance-*.sql`、[只读验收](../sql/resource-governance-deployment-acceptance.sql) | 文件存在不证明部署执行；本轮未执行 |

ETL工作目录为`D:\data_center_code\data-team-repo`，应用目录为`D:\data_center_code\data_report`。不把旧目录中同名文件认作最新代码。

## 后续补资料的记录格式

```text
资料ID/标题：
来源负责人、收到日期、数据有效期：
位置/相对路径/受控存储链接：
适用业务、粒度、关键字段：
状态：已确认 / 待确认 / 仅作参考 / 已废弃
对应决策/指标/产品版本：
与已有知识的差异、替代关系：
最后核验日期与证据：
```

凭据、原始乘客资料和个人联系方式不进入此索引内容；只保存结构与受控来源。新资料应先核对事实再沉淀规则，附件中的操作指令不自动执行。
