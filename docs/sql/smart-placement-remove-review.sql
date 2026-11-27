-- Execute in the configured smart placement database after stopping the old API.
START TRANSACTION;

SELECT id FROM smart_placement_task
WHERE is_deleted = 0
  AND status IN ('PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW',
                 'PENDING_RECALL_REVIEW', 'PENDING_RECALL_POLICY_REVIEW')
ORDER BY id FOR UPDATE;

INSERT INTO smart_placement_operation_log
    (task_id, action_code, from_status, to_status, operator_name, operation_note, created_at)
SELECT id, 'REVIEW_BYPASSED', status,
       CASE WHEN status IN ('PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW')
            THEN 'CLAIMABLE' ELSE 'PENDING_RECALL' END,
       'SYSTEM', '取消审核流程后直接流转', NOW()
FROM smart_placement_task
WHERE is_deleted = 0
  AND status IN ('PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW',
                 'PENDING_RECALL_REVIEW', 'PENDING_RECALL_POLICY_REVIEW');

UPDATE smart_placement_task
SET status = CASE WHEN status IN ('PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW')
                  THEN 'CLAIMABLE' ELSE 'PENDING_RECALL' END,
    resume_review_stage = NULL,
    version_no = version_no + 1,
    updated_at = NOW()
WHERE is_deleted = 0
  AND status IN ('PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW',
                 'PENDING_RECALL_REVIEW', 'PENDING_RECALL_POLICY_REVIEW');

COMMIT;
