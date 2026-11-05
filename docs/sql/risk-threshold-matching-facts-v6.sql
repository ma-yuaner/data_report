-- RISK-CHECK-002，MySQL只读。航段参数：issue_id, order_id；机场参数：airport_code。
-- 源码 risk_threshold_facts.py；单票航段不完整/重复/超200或多段字段不一致均不猜值。

-- SEGMENTS_SQL
SELECT s.id,s.order_id,s.cabin,s.cabin_grade,s.flight_number,s.dep_airport,s.arr_airport,
 s.journey_sequence,s.segment_sequence
 FROM order_info_issue_segment i JOIN order_info_segment s ON s.id=i.segment_id
 WHERE i.issue_id=%s AND s.order_id=%s AND s.airlift_flag=1
 ORDER BY s.journey_sequence,s.segment_sequence,s.id LIMIT 201;

-- AIRPORT_SQL
SELECT airport_code,city_code,country_code,zone_code,area_code,update_time
 FROM base_airport WHERE airport_code=%s AND status=1 LIMIT 2;

-- 用户确认dep_city/arr_city是主航段机场；参数为order_id。
SELECT id,ota_code,ota_site_code,product_type,manual_flag,issue_way,dep_city,arr_city,profit_reason_type,update_time FROM order_info WHERE id=%s;
