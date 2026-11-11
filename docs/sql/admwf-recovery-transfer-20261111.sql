-- 主单恢复与转派。先确保主单已有 line_defaults_json；只执行尚未存在的列。
ALTER TABLE admwf_case
  ADD COLUMN airline_name VARCHAR(100) NULL COMMENT '主单关联航司名称，与下发方独立',
  ADD COLUMN master_recovery_status VARCHAR(32) NULL COMMENT '主单恢复编码阶段；NULL为旧明细恢复流程',
  ADD COLUMN recovery_locators VARCHAR(2000) NULL COMMENT '组长提交的GDS-PCC-PNR定位串，逗号分隔',
  ADD COLUMN master_recovery_due_at DATETIME NULL COMMENT '负责人标记正在恢复后48小时的到期时点',
  ADD COLUMN leader_overdue_at DATETIME NULL COMMENT '发现组长主单待办超过72小时的标签记录时间',
  ADD COLUMN leader_first_action_at DATETIME NULL COMMENT '初始组长首次恢复判断或转派的操作时间',
  ADD COLUMN pending_leader_transfer_json JSON NULL COMMENT '明细产生前主单组长待确认转派；保存原及目标账号、原因和申请时间';

ALTER TABLE admwf_case_line
  ADD COLUMN leader_overdue_at DATETIME NULL COMMENT '超过最初派组长72小时未分配、接单或转派的标签记录时间',
  ADD COLUMN operator_overdue_at DATETIME NULL COMMENT '超过最初派操作员72小时未接单或转派的标签记录时间';

ALTER TABLE admwf_transfer
  ADD COLUMN target_role VARCHAR(16) NOT NULL DEFAULT 'OPERATOR'
    COMMENT '转派责任岗位：LEADER组长或OPERATOR操作员，既有记录为操作员';
