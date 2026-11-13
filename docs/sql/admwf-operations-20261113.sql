-- ADM运营：新增三张辅助表，并扩展两列问题归因类型；在ADM数据库执行，MySQL 5.7+/8.0。
CREATE TABLE IF NOT EXISTS admwf_line_context (
 line_id BIGINT NOT NULL COMMENT '订单明细ID，一笔明细一条当前原因记录',
 case_id BIGINT NOT NULL COMMENT '所属ADM主单ID，由应用事务校验一致',
 cause_category VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN' COMMENT '根因：HUMAN人为/SYSTEM系统/EXTERNAL外部规则平台/BUSINESS业务/FORCE_MAJEURE不可抗力/UNKNOWN待查明',
 cause_detail TEXT NULL COMMENT '根本原因及调查结论，不以罚单事项代替根因',
 evidence_note TEXT NULL COMMENT '证据说明或附件引用，不存附件正文',
 blocking_reason TEXT NULL COMMENT '当前阻塞原因，解决后可更新',
 responsible_link VARCHAR(2000) NULL COMMENT '涉及责任环节，例如订位、出票或退款，不表示已认定个人责任',
 updated_by_id BIGINT NOT NULL COMMENT '最后补充信息的中台用户ID',
 updated_at DATETIME NOT NULL COMMENT '最后更新时间，Asia/Shanghai业务本地时间',
 PRIMARY KEY(line_id), KEY idx_context_case(case_id), KEY idx_context_cause(cause_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM订单过程原因、证据和阻塞信息，历史变更见既有操作日志';
CREATE TABLE IF NOT EXISTS admwf_operations_config (
 id INT NOT NULL COMMENT '固定1，运营配置单例',
 settings_json JSON NOT NULL COMMENT '配置：enabled开关、endpointId现有群端点ID、times每日1到2个HH:mm、slaHours各阶段小时、baseUrl页面地址；不存Webhook密钥',
 updated_by_id BIGINT NOT NULL COMMENT '配置修改人中台ID',
 updated_at DATETIME NOT NULL COMMENT '配置修改时间，Asia/Shanghai',
 PRIMARY KEY(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM阶段时限和每日群提醒配置，未配置默认不发送';
CREATE TABLE IF NOT EXISTS admwf_reminder_delivery (
 id BIGINT NOT NULL AUTO_INCREMENT COMMENT '发送记录ID',
 delivery_key CHAR(64) NOT NULL COMMENT '日期时段与群端点ID的SHA256去重键',
 slot_key VARCHAR(32) NOT NULL COMMENT '计划时段YYYY-MM-DD HH:mm，Asia/Shanghai',
 endpoint_id VARCHAR(64) NOT NULL COMMENT '监控中心企业微信群端点ID，不存地址或密钥',
 status VARCHAR(16) NOT NULL COMMENT 'CLAIMED已占用/SENT已送达/FAILED平台明确失败/UNKNOWN网络结果不明/SKIPPED无待办',
 task_count INT NOT NULL COMMENT '本次汇总当前有效待办项数',
 message_summary TEXT NOT NULL COMMENT '实际发送文本，包含单号和责任人，不包含PNR票号及Webhook',
 created_at DATETIME NOT NULL COMMENT '发送占用时间，Asia/Shanghai',
 finished_at DATETIME NULL COMMENT '本地发送完成时间，未知或进程中断可空',
 PRIMARY KEY(id), UNIQUE KEY uq_adm_delivery(delivery_key), KEY idx_adm_delivery_time(created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM群提醒去重与发送证据；不自动重试结果不明的消息';

-- 保留原归因值，扩展业务与不可抗力等归因；若原列为ENUM，显式转换为VARCHAR(32)。
ALTER TABLE admwf_case_line MODIFY COLUMN problem_attribution VARCHAR(32) NULL COMMENT '订单问题根因：HUMAN/PLATFORM兼容旧平台/SYSTEM/EXTERNAL/BUSINESS/FORCE_MAJEURE/UNKNOWN';
ALTER TABLE admwf_appeal MODIFY COLUMN problem_attribution VARCHAR(32) NULL COMMENT '本轮申诉问题根因，支持人为系统外部业务不可抗力及待查明，保留历史原值';
