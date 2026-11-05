-- Read-only review query based on user-provided tables.
-- Current candidates only: not historical matching, not a single stop-loss value.
SELECT r.id,r.rule_name,r.ota_code,r.ota_site_code,r.rule_type,r.rule_group_type,
       r.start_time,r.end_time,r.update_time,r.version,r.rule_notes,r.ext_json
FROM base_issue_match_rule r
WHERE r.rule_business_type='RB01' AND r.status=1
  AND EXISTS (SELECT 1 FROM system_com_type_det d
              WHERE d.det_code=r.rule_group_type AND d.parent_code='SYS_RULE_GROUP_TYPE_ISSUE'
                AND d.det_cname IN ('出票盈亏配置','出票规则配置'))
ORDER BY r.update_time DESC,r.id DESC
LIMIT 201;
-- sibe_ota: ota_code; sibe_ota_site: ota_code + ota_site_code.
-- Dictionary joins require parent_code + det_code uniqueness validation.
-- base_issue_match_log.business_obj_id may link many logs per rule: query separately,
-- and establish business-object scope before using them for historical reconstruction.
-- Do not put log timestamp predicates in WHERE when retaining unmatched rules.
