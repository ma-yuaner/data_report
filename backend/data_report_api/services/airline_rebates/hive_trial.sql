SELECT airport_code, country_code FROM lywz.dim_base_airport_full
WHERE status = 1 AND airport_code IS NOT NULL AND country_code IS NOT NULL;

SELECT order_id, issue_ticket_no, segment_airport, first_dep_time, segment_real_cabin,
       issue_ticket_price, issue_currency, dep_airport, arr_airport, real_age_type_desc,
       refund_flag_desc, issue_ticket_no_status, refund_issue_flag, issue_price_type_desc,
       segment_dep_time, segment_marketing_airline, flt_status
FROM lywz.dwd_order_issue_wide_year
WHERE supplier_code = 'HK_NGCHOW'
  AND order_status = 'TICKETED' AND issue_status = 'I_UPDATED'
  AND (issue_ticket_no_status IS NULL OR issue_ticket_no_status NOT IN (2, 3))
  AND COALESCE(refund_flag_desc, '') NOT IN ('已退票', '废票', '已作废')
  AND COALESCE(flt_status, '') NOT IN ('R', 'V')
  AND SUBSTR(issue_ticket_no, 1, 3) = %s
  AND ((first_dep_time >= %s AND first_dep_time < %s) OR segment_dep_time RLIKE %s)
ORDER BY first_dep_time, id
LIMIT 50001;
