-- Hive利润核对表金额精度迁移：DECIMAL(18,4) -> DECIMAL(18,8)
-- 来源：用户2026-09-29确认的三张MySQL BI表字段精度。
-- Hive CHANGE COLUMN 一次只修改一列；三张目标表均为非分区表，不使用CASCADE。
-- 注意：Hive ALTER只修改元数据。执行前请先备份/确认现有ORC可按新精度读取，
-- 执行后用DESCRIBE核验，再重新提交数据上传任务完成整表重写。

USE lywz;

-- 出票：dwd_order_issue_profit_reconcile_year
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN receivable_org_amount receivable_org_amount DECIMAL(18,8) COMMENT '应收原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN received_org_amount received_org_amount DECIMAL(18,8) COMMENT '实收原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN receivable_cny_amount receivable_cny_amount DECIMAL(18,8) COMMENT '应收CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN received_cny_amount received_cny_amount DECIMAL(18,8) COMMENT '实收CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN sale_commission_cny_amount sale_commission_cny_amount DECIMAL(18,8) COMMENT '佣金CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN sale_fx_gain_loss_cny sale_fx_gain_loss_cny DECIMAL(18,8) COMMENT '销售汇兑损益';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN ticket_price_org_amount ticket_price_org_amount DECIMAL(18,8) COMMENT '票面原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN tax_org_amount tax_org_amount DECIMAL(18,8) COMMENT '税额原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN fee_org_amount fee_org_amount DECIMAL(18,8) COMMENT '手续费原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN supplier_front_rebate_org_amount supplier_front_rebate_org_amount DECIMAL(18,8) COMMENT '供应商前返原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN supplier_back_rebate_org_amount supplier_back_rebate_org_amount DECIMAL(18,8) COMMENT '供应商后返原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN payable_org_amount payable_org_amount DECIMAL(18,8) COMMENT '应付原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN paid_org_amount paid_org_amount DECIMAL(18,8) COMMENT '实付原币金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN payable_cny_amount payable_cny_amount DECIMAL(18,8) COMMENT '应付CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN paid_cny_amount paid_cny_amount DECIMAL(18,8) COMMENT '实付CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN purchase_fx_gain_loss_cny purchase_fx_gain_loss_cny DECIMAL(18,8) COMMENT '采购汇兑损益';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN segment_reward_cny_amount segment_reward_cny_amount DECIMAL(18,8) COMMENT '航段奖励CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN payment_card_rebate_cny_amount payment_card_rebate_cny_amount DECIMAL(18,8) COMMENT '支付卡返CNY';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN supplier_back_rebate_cny_amount supplier_back_rebate_cny_amount DECIMAL(18,8) COMMENT '供应商后返CNY金额';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN estimated_profit_cny estimated_profit_cny DECIMAL(18,8) COMMENT '预估利润(公式)';
ALTER TABLE dwd_order_issue_profit_reconcile_year CHANGE COLUMN actual_profit_cny actual_profit_cny DECIMAL(18,8) COMMENT '实际利润(推算)';

-- 退票：dwd_order_refund_profit_reconcile_year
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN refund_due_org_amount refund_due_org_amount DECIMAL(18,8) COMMENT '应退原币金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN refund_actual_org_amount refund_actual_org_amount DECIMAL(18,8) COMMENT '实退原币金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN refund_due_cny_amount refund_due_cny_amount DECIMAL(18,8) COMMENT '应退CNY金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN refund_actual_cny_amount refund_actual_cny_amount DECIMAL(18,8) COMMENT '实退CNY金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN sale_commission_cny_amount sale_commission_cny_amount DECIMAL(18,8) COMMENT '佣金CNY金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN refund_fee_org_amount refund_fee_org_amount DECIMAL(18,8) COMMENT '手续费原币金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN supplier_refund_receivable_org_amount supplier_refund_receivable_org_amount DECIMAL(18,8) COMMENT '应收退款原币';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN supplier_refund_received_org_amount supplier_refund_received_org_amount DECIMAL(18,8) COMMENT '实收退款原币';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN supplier_refund_receivable_cny_amount supplier_refund_receivable_cny_amount DECIMAL(18,8) COMMENT '应收退款CNY';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN supplier_refund_received_cny_amount supplier_refund_received_cny_amount DECIMAL(18,8) COMMENT '实收退款CNY';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN supplier_refund_fx_gain_loss_cny supplier_refund_fx_gain_loss_cny DECIMAL(18,8) COMMENT '实收退款汇兑损益';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN segment_reward_cny_amount segment_reward_cny_amount DECIMAL(18,8) COMMENT '航段奖励CNY金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN payment_card_rebate_cny_amount payment_card_rebate_cny_amount DECIMAL(18,8) COMMENT '支付卡返CNY';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN supplier_back_rebate_cny_amount supplier_back_rebate_cny_amount DECIMAL(18,8) COMMENT '供应商后返CNY金额';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN estimated_profit_cny estimated_profit_cny DECIMAL(18,8) COMMENT '预估利润(公式)';
ALTER TABLE dwd_order_refund_profit_reconcile_year CHANGE COLUMN actual_profit_cny actual_profit_cny DECIMAL(18,8) COMMENT '实际利润(推算)';

-- 改签：dwd_order_change_profit_reconcile_year
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN receivable_org_amount receivable_org_amount DECIMAL(18,8) COMMENT '应收原币金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN received_org_amount received_org_amount DECIMAL(18,8) COMMENT '实收原币金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN receivable_cny_amount receivable_cny_amount DECIMAL(18,8) COMMENT '应收CNY金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN received_cny_amount received_cny_amount DECIMAL(18,8) COMMENT '实收CNY金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN sale_fx_gain_loss_cny sale_fx_gain_loss_cny DECIMAL(18,8) COMMENT '销售汇兑损益';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN payable_org_amount payable_org_amount DECIMAL(18,8) COMMENT '应付原币金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN paid_org_amount paid_org_amount DECIMAL(18,8) COMMENT '实付原币金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN payable_cny_amount payable_cny_amount DECIMAL(18,8) COMMENT '应付CNY金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN paid_cny_amount paid_cny_amount DECIMAL(18,8) COMMENT '实付CNY金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN purchase_fx_gain_loss_cny purchase_fx_gain_loss_cny DECIMAL(18,8) COMMENT '采购汇兑损益';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN segment_reward_cny_amount segment_reward_cny_amount DECIMAL(18,8) COMMENT '航段奖励CNY金额';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN payment_card_rebate_cny_amount payment_card_rebate_cny_amount DECIMAL(18,8) COMMENT '虚拟卡返CNY';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN estimated_profit_cny estimated_profit_cny DECIMAL(18,8) COMMENT '预估利润';
ALTER TABLE dwd_order_change_profit_reconcile_year CHANGE COLUMN actual_profit_cny actual_profit_cny DECIMAL(18,8) COMMENT '实际利润(推算)';

DESCRIBE dwd_order_issue_profit_reconcile_year;
DESCRIBE dwd_order_refund_profit_reconcile_year;
DESCRIBE dwd_order_change_profit_reconcile_year;
