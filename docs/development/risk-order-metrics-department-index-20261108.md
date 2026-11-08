# 当天指标部门关联索引缺失

用户任务678159/1716031，Worker218，2026-11-08 16:10运行：scope=today、historicalChangeScan=false；当天目录1887行已确认发布，已接规则准备1654单，其中supported1622、problem32、复用1444；61.28秒完成该日。随后lifecycle_metrics报METRIC_DEPARTMENT_ORDER_INDEX_MISSING，最终partial_failure/退出1。不是当天目录回滚、不是再处理历史；规则核对与部门/利润指标必须分开说明。

16:13真实只读元数据：MySQL5.7.44-log，sibebid.bi_order_issue_profit_reconcile_year为InnoDB，TABLE_ROWS估计38429（非精确行数）；order_no和org_cname均varchar(150)、可NULL、默认NULL、utf8_general_ci。现有日期、航司、部门、平台、站点、供应商索引没有order_no首列。R2将已有指标入口接入自动链后暴露之前未满足的部署前置，不移除门禁或回退全表扫描。

## 表与变更用途

既有表用于出票利润核对明细，原业务粒度/主键及留存不在本轮更改。风控仅按目录order_no关联业务部门，可能一单多部门，返回去重部门集合，不代表责任认定、不将部门行相加当订单数。实际表/列COMMENT回读存在乱码，本轮只增加有中文COMMENT的新索引，不擅自重写已有列/表注释。

| 受影响字段 | 中文含义与来源 | 实库类型/NULL/默认 | 关联与约束 | 本轮变化 |
|---|---|---|---|---|
| order_no | 内部业务订单号，对应风控目录来自ERP order_info.order_no；不是OTA订单号 | varchar(150)，NULL允许/默认NULL，utf8_general_ci；NULL为未知，不补空串 | 原表可有多行，不新增唯一约束 | 新增完整BTREE非唯一首列索引idx_risk_reconcile_order_no |
| org_cname | 出票核对表业务归属部门，风控仅作分析归属 | varchar(150)，NULL允许/默认NULL，utf8_general_ci；未知部门不补0 | order_no关联后GROUP BY去重，可一对多 | 不修改字段，继续按原语义读取 |

DDL文件docs/sql/risk-order-metrics-department-index-v1.sql：如已有任意完整order_no首列索引则跳过，否则ADD INDEX；声明ALGORITHM=INPLACE/LOCK=NONE，不支持时失败，不自动改锁表方案。仍可能等待元数据锁，索引有构建与后续写维护成本；未执行不能声称无锁/耗时通过。同名错误索引不会被自动删除。无数据回填/覆盖、无列类型或默认值变更；索引保留不影响旧代码读取，不提供自动DROP回滚。

## 操作及验收

由获授权人在sibebid执行该单个SQL文件，回读完整索引及EXPLAIN；不重复已有指标两表或阈值四表DDL。随后重跑原生命周期任务，检查metricDays/metrics_complete成功；当天目录已发布不必清队列或删数据。原任务如果当天仍新鲜无需重做准备也会尝试补指标；若到5分钟补偿门槛，按原约定重新核对当天。再跑当天分析以更新利润/部门桶，查看页面。索引成功不能替代指标覆盖、分析或业务验收。

本轮主会话只读核验、DDL提供和源码归档，未执行生产DDL/写入。字段/索引证据ETL var/risk-cleaning/department-index-readonly.json，SQL资产RISK-DDL-045/核验RISK-CHECK-044。MySQL5.7语法按实库字段契约准备，实际DDL与元数据注释/计划执行仍待回执。
