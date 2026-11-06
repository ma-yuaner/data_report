-- Dedicated team review tables. Deploy explicitly to approved sibebid; no ERP changes.
-- Preserve all existing automatic results, samples and legacy cases.
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_followup_cases (
 id CHAR(32) NOT NULL PRIMARY KEY COMMENT '案例唯一编号，由应用随机生成',
 version INT NOT NULL COMMENT '案例并发版本，每次有效修改递增',
 conclusion VARCHAR(20) NOT NULL COMMENT '人工实际问题结论：no_issue无问题、problem有问题、unknown暂无法判断',
 disposition VARCHAR(20) NOT NULL COMMENT '当前差错认定：pending待认定、included计入、excluded不计入',
 state VARCHAR(20) NOT NULL COMMENT '跟进状态：todo待跟进、following跟进中、waiting等待反馈、done已完成',
 assignee VARCHAR(80) NOT NULL COMMENT '实际跟进负责人姓名，不代表数据库账号授权',
 next_at VARCHAR(40) NULL COMMENT '下次跟进时间，Asia/Shanghai带时区ISO字符串，已完成为NULL',
 first_seen TINYINT NOT NULL DEFAULT 0 COMMENT '是否人工确认首次出现：1是、0否，默认0不自动推断',
 special TINYINT NOT NULL DEFAULT 0 COMMENT '是否人工标记特殊案例：1是、0否，默认0',
 body LONGTEXT NOT NULL COMMENT '完整案例JSON快照，含标题、原因、责任归属、下一步、标记依据及创建时间',
 updated_at VARCHAR(40) NOT NULL COMMENT '最近有效修改时间，Asia/Shanghai带时区ISO字符串',
 KEY ix_risk_case_pool (conclusion,disposition,state),
 KEY ix_risk_case_follow (assignee,state,next_at),
 KEY ix_risk_case_updated (updated_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控共享跟进案例：一行一个跨订单案例，认定与跟进状态独立';
CREATE TABLE IF NOT EXISTS bi_risk_order_reviews (
 order_id VARCHAR(40) NOT NULL COMMENT 'ERP内部订单ID字符串，不保存旅客身份信息',
 issue_date DATE NOT NULL COMMENT '关联证据的出票业务日期，Asia/Shanghai',
 version INT NOT NULL COMMENT '本订单本出票日人工核实版本，每次核实或结论变更递增',
 case_id CHAR(32) NULL COMMENT '关联跟进案例编号，单独确认无问题可为NULL',
 body LONGTEXT NOT NULL COMMENT '人工核实JSON快照，含系统证据身份、人工结论、策略快照、依据和操作者',
 PRIMARY KEY (order_id,issue_date),
 KEY ix_risk_review_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单人工核实当前记录：一行一个内部订单ID和出票日组合';
CREATE TABLE IF NOT EXISTS bi_risk_followup_events (
 seq BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '历史事件自增序号，用于稳定展示最近操作',
 id CHAR(32) NOT NULL UNIQUE COMMENT '事件唯一随机编号，防止重复标识',
 case_id CHAR(32) NULL COMMENT '关联案例编号，独立无问题核实时可为NULL',
 order_id VARCHAR(40) NULL COMMENT '订单级核实事件的内部订单ID，案例级跟进事件为NULL',
 issue_date DATE NULL COMMENT '订单级核实事件关联出票日，案例级事件为NULL',
 body LONGTEXT NOT NULL COMMENT '事件JSON，含操作人、业务时间、类型、修改前后快照和依据',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '数据库写入时间戳，由数据库CURRENT_TIMESTAMP生成，连接时区须核对',
 KEY ix_risk_event_case (case_id,seq),
 KEY ix_risk_event_order (order_id,issue_date,seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工核实及案例跟进追加历史：一行一次有效操作事件，不覆盖旧记录';
CREATE TABLE IF NOT EXISTS bi_risk_review_policies (
 id CHAR(32) NOT NULL PRIMARY KEY COMMENT '策略版本唯一随机编号，历史核实保存本版本快照',
 body LONGTEXT NOT NULL COMMENT '策略JSON，含名称、版本、适用出票日起止、适用范围、认可依据和登记人',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '数据库登记时间戳，默认CURRENT_TIMESTAMP，连接时区须核对'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公司策略不可变版本登记：一行一个由业务认可并人工登记的具体策略版本';
CREATE TABLE IF NOT EXISTS bi_risk_followup_requests (
 id VARCHAR(80) NOT NULL PRIMARY KEY COMMENT '前端每份草稿固定请求标识，失败重试沿用，不是凭据',
 actor VARCHAR(80) NOT NULL COMMENT '发起操作的已认证账号ID，由服务端取得',
 digest CHAR(64) NOT NULL COMMENT '规范化请求内容的SHA256摘要，用于拒绝同键不同内容',
 response LONGTEXT NOT NULL COMMENT '成功业务响应JSON，用于重复请求返回同一结果',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '数据库回执写入时间戳，默认CURRENT_TIMESTAMP，连接时区须核对'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工跟进写入幂等回执：一行一个操作草稿的唯一请求，和业务写入同事务';
