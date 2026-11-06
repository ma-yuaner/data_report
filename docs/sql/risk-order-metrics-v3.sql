-- 风控V3订单展示指标。部署人显式在sibebid执行；应用/ETL不自动建表。
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_order_metric_day (
 issue_date DATE NOT NULL COMMENT '目录出票业务日，Asia/Shanghai；跨日查询按订单取范围内最后日',
 order_id BIGINT NOT NULL COMMENT 'ERP内部订单ID，与同日目录一对一',
 catalog_run_id VARCHAR(64) CHARACTER SET ascii NOT NULL COMMENT '关联目录发布批次；不匹配时指标不可用',
 total_profit DECIMAL(28,4) NULL COMMENT '订单全部出票明细issue_profit原值之和，CNY；任一缺失则NULL，不加佣金',
 segment_count INT NULL COMMENT '订单airlift_flag=1的航空段去重数；来源缺失或标记未知则NULL',
 body LONGTEXT NOT NULL COMMENT 'V3指标JSON：航司和业务部门数组、缺失标记及部门来源说明；不含乘客/票号',
 measured_at DATETIME(6) NOT NULL COMMENT '本次只读源快照的指标加工时间，Asia/Shanghai',
 PRIMARY KEY(issue_date,order_id),
 KEY ix_risk_metric_profit(issue_date,total_profit,order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控V3目录订单总利润和航空段指标，只由独立清洗按日原子发布';
CREATE TABLE IF NOT EXISTS bi_risk_order_metric_day_ready (
 issue_date DATE NOT NULL COMMENT '完成指标加工的出票业务日，零单也留覆盖',
 catalog_run_id VARCHAR(64) CHARACTER SET ascii NOT NULL COMMENT '完整加工时核对的目录批次',
 row_count BIGINT NOT NULL COMMENT '该批次指标行数，含指标缺失行；零不等于未同步',
 measured_at DATETIME(6) NOT NULL COMMENT '该日原子发布完成时刻，Asia/Shanghai',
 PRIMARY KEY(issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控V3订单指标逐日完整覆盖，与明细同事务发布';
