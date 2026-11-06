-- 用户/数据库部署人显式执行；仅新增两张证据表，不修改ERP、原清洗结果或原跟进表。
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_config_evidence (
 id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY COMMENT '固定证据唯一随机编号',
 order_id VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'ERP内部订单ID，字符串保留完整标识',
 issue_date DATE NOT NULL COMMENT '原核对关联出票业务日，Asia/Shanghai',
 original_result_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '保存时已发布日事实的稳定核对结果ID',
 body LONGTEXT NOT NULL COMMENT '不可覆盖的原核对JSON，含逐票止损、结果、配置身份快照和历史证明、保存人时间及哈希',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '数据库首次写入时间，连接时区须回读核对',
 UNIQUE KEY uq_risk_evidence_order (order_id,issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='订单原配置证据：一行一订单出票日，首次保存后应用不覆盖';
CREATE TABLE IF NOT EXISTS bi_risk_config_observations (
 seq BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '观察事件递增序号，用于同一证据的最新观察排序',
 id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE COMMENT '本次观察事件唯一随机编号',
 evidence_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '逻辑关联原证据ID，原证据一对多观察',
 request_id VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE COMMENT '观察草稿的固定幂等标识，重试不重复查询和写入',
 request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '发起人和请求内容SHA256，拒绝同键不同请求',
 body LONGTEXT NOT NULL COMMENT '追加观察JSON，含原值上次值最新值、源版本快照、观察时间、更新时间及未证实生效时间说明',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '数据库追加写入时间，非源变更生效时间',
 KEY ix_risk_observation_evidence (evidence_id,seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='配置最新值观察历史：一行一次显式观察，仅提醒不参与原单核算';
