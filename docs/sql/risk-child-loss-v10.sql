-- RISK-CHECK-004，MySQL只读，参数通过PyMySQL绑定；不含实际订单号或旅客明细。

-- 根订单参数order_id；dep_city/arr_city实为主航段机场。
SELECT id,ota_code,ota_site_code,product_type,manual_flag,issue_way,dep_city,arr_city,ota_order_no,relation_ota_order_no,profit_reason_type,update_time FROM order_info WHERE id=%s;

-- 携程关联闭包：参数ota_code=CTRIP、站点（NULL安全）、一组OTA编号重复绑定。
-- 以下为单编号形态；源码按编号数生成IN占位符，重复查到的节点只遍历一次，独立出票不去重。
SELECT id,ota_code,ota_site_code,product_type,manual_flag,issue_way,dep_city,arr_city,ota_order_no,relation_ota_order_no,profit_reason_type,update_time FROM order_info WHERE ota_code=%s AND ota_site_code <=> %s AND (ota_order_no IN (%s) OR relation_ota_order_no IN (%s)) ORDER BY id LIMIT 101;

-- 年龄类型：参数order_id；ADU成人/CHD儿童/INF婴儿。
SELECT i.id,p.age_type FROM order_info_issue i LEFT JOIN order_info_passenger p ON p.id=i.passenger_id AND p.order_id=i.order_id WHERE i.order_id=%s ORDER BY i.id LIMIT 201;

-- 手工批次支持的原因，参数RLA013、RLA040；指定某原因时仅生成一个占位符。
SELECT order_id AS id,profit_reason_type,update_time FROM risk_order_day_stage WHERE profit_reason_type IN (%s,%s) ORDER BY order_id LIMIT 2001;

-- 来源字典核验参数PRODUCT_PROFIT_REASON_TYPE、%儿童%、%婴儿%、AGE_TYPE、PASSENGER_TYPE。
SELECT parent_code,det_code,det_cname FROM system_com_type_det WHERE (parent_code=%s AND (det_cname LIKE %s OR det_cname LIKE %s)) OR parent_code IN (%s,%s);

-- 本轮有限样本核验参数RLA040及起止出票日期，最多5单；携程专项追加o.ota_code=%s，绑定CTRIP。
SELECT DISTINCT o.id FROM order_info o JOIN order_info_issue i ON i.order_id=o.id WHERE o.profit_reason_type=%s AND i.issue_ticket_time >= %s AND i.issue_ticket_time < %s ORDER BY o.id DESC LIMIT 5;

-- 复用既有取证SQL，参数分别为order_id；或order_id、issue_id。
SELECT id,order_id,issue_profit,sale_commission_amount,sale_currency,issue_ticket_time,
      supplier_code,marketing_airline,issue_gds_channel,issue_office_no,issue_ticketing_office_no
      FROM order_info_issue WHERE order_id=%s ORDER BY id LIMIT 201;

-- 复用既有取证SQL，参数分别为order_id；或order_id、issue_id。
SELECT COUNT(*) AS link_count,COUNT(DISTINCT s.id) AS segment_count
              FROM order_info_issue_segment i LEFT JOIN order_info_segment s ON s.id=i.segment_id
              AND s.order_id=%s AND s.airlift_flag=1 WHERE i.issue_id=%s;
