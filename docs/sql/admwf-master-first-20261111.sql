-- ADM 主单建档后补录订单明细。先在目标中台 ADM 库核对列是否已存在，再执行一次。
-- 旧主单保持 NULL，按已有明细资料办理；无需批量回填。
ALTER TABLE admwf_case
  ADD COLUMN line_defaults_json JSON NULL
    COMMENT '主单录入的订单明细继承资料：归属部门、负责组长、差异类型和细分差异原因；NULL为原流程主单';
