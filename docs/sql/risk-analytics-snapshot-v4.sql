-- 风控分析V4：调度预汇总，HTTP只读快照。部署人显式执行，不在ERP执行。
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_analytics_snapshot (
 end_date DATE NOT NULL COMMENT '查询结束日期；每份支持结束日前30日至当天任意起日',
 snapshot_id CHAR(32) CHARACTER SET ascii NULL COMMENT '成功发布快照代次；NULL表示尚未生成，不得显示为0',
 schema_version VARCHAR(40) CHARACTER SET ascii NOT NULL COMMENT '聚合契约版本，V4与旧版本不混读',
 source_signature CHAR(64) CHARACTER SET ascii NULL COMMENT '目录/核查/指标批次及人工记录版本签名，未变化不重复计算',
 source_cutoff DATETIME(6) NULL COMMENT '一致性读取开始时刻，Asia/Shanghai；不是ERP实时核查时刻',
 generated_at DATETIME(6) NULL COMMENT '本份汇总生成完成时刻，Asia/Shanghai',
 checked_at DATETIME(6) NULL COMMENT '调度最近成功核对来源签名时刻，未变时不改生成时间',
 requested_at DATETIME(6) NOT NULL COMMENT '最近查询请求或当日定时刷新请求时刻',
 request_generation BIGINT NOT NULL COMMENT '请求代次递增，防止处理过程中到达的新请求丢失',
 processed_generation BIGINT NOT NULL COMMENT '本次已完成请求代次；小于请求代次表示待刷新',
 retry_after DATETIME(6) NOT NULL COMMENT '失败退避后允许重试时刻，Asia/Shanghai',
 last_error_code VARCHAR(100) CHARACTER SET ascii NULL COMMENT '最近刷新安全错误码；保留旧快照，不存原始数据库错误',
 order_count BIGINT NULL COMMENT '31日窗口去重订单数；NULL未生成，0为已生成空结果',
 body LONGTEXT NULL COMMENT '快照JSON：窗口、源日覆盖及规则/字典版本，不含逐单或乘客明细',
 PRIMARY KEY(end_date),
 KEY ix_risk_analytics_due(retry_after,requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控分析调度快照及请求队列；一个结束日期一份原子发布版本';
CREATE TABLE IF NOT EXISTS bi_risk_analytics_bucket (
 end_date DATE NOT NULL COMMENT '所属查询结束日期，与快照清单关联',
 issue_date DATE NOT NULL COMMENT '该结束日下每个订单的最后出票日，跨日订单只落一个分桶',
 dimension VARCHAR(16) CHARACTER SET ascii NOT NULL COMMENT 'total总量、category原因分类、department业务部门',
 group_hash CHAR(64) CHARACTER SET ascii NOT NULL COMMENT '维度原值SHA256，与日期/维度构成主键',
 group_key VARCHAR(200) NOT NULL COMMENT '真实分类编码或部门原值，总量为total，不拼接用户SQL',
 group_label VARCHAR(500) NOT NULL COMMENT '该快照的分类或部门显示名称，不代表责任认定',
 snapshot_id CHAR(32) CHARACTER SET ascii NOT NULL COMMENT '发布代次，必须等于对应清单，避免读取混合版本',
 orders BIGINT NOT NULL COMMENT '该分桶去重订单数；部门多归属行不可相加为总量',
 auto_passed BIGINT NOT NULL COMMENT '当前有效自动通过订单数',
 auto_concluded BIGINT NOT NULL COMMENT '自动通过加疑似问题订单数，不含证据不足',
 human_reviewed BIGINT NOT NULL COMMENT '当前有效人工无问题或有问题订单数',
 human_problems BIGINT NOT NULL COMMENT '当前有效人工有问题订单数',
 included_errors BIGINT NOT NULL COMMENT '当前有效人工问题且案例计入差错订单数',
 profit_missing BIGINT NOT NULL COMMENT '利润缺失或指标批次未就绪订单数；大于0则该组正式合计为空',
 known_profit DECIMAL(38,4) NOT NULL COMMENT '已知整单出票利润之和，CNY；存在缺失不得冒充完整合计',
 known_loss DECIMAL(38,4) NOT NULL COMMENT '已知负利润订单利润之和，CNY，保留负号',
 PRIMARY KEY(end_date,issue_date,dimension,group_hash),
 KEY ix_risk_analytics_read(end_date,snapshot_id,issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控分析调度后的日分桶；任意1至31日范围只汇总桶，不读取逐单事实';
