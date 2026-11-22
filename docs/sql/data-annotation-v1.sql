-- 在数据中台 MYSQL_DATABASE 对应的 MySQL 库执行。只创建独立标注表。
CREATE TABLE IF NOT EXISTS annotation_project (
  id CHAR(32) NOT NULL COMMENT '系统分配的标注项目ID',
  name VARCHAR(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '项目名称，忽略大小写唯一',
  owner_id VARCHAR(20) NOT NULL COMMENT '项目负责人中台账号ID',
  kind VARCHAR(12) NOT NULL COMMENT '项目类型：adm或general',
  version_no INT UNSIGNED NOT NULL COMMENT '项目配置并发版本，从1开始递增',
  labels LONGTEXT NOT NULL COMMENT '字段和文件标签定义JSON，包含稳定ID、名称、说明与层级',
  PRIMARY KEY (id),
  UNIQUE KEY uk_annotation_project_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标注项目及其当前标签配置，每项目一行';

CREATE TABLE IF NOT EXISTS annotation_member (
  project_id CHAR(32) NOT NULL COMMENT '所属标注项目ID',
  account_id VARCHAR(20) NOT NULL COMMENT '获授权项目成员的中台账号ID',
  role VARCHAR(12) NOT NULL COMMENT '项目角色：annotator标注员或reviewer复核人',
  display_name VARCHAR(120) NOT NULL COMMENT '配置时的成员显示名称，账号ID为授权依据',
  PRIMARY KEY (project_id,account_id),
  KEY idx_annotation_member_account (account_id,project_id),
  CONSTRAINT fk_annotation_member_project FOREIGN KEY (project_id) REFERENCES annotation_project(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成员授权，每项目每账号一行';

CREATE TABLE IF NOT EXISTS annotation_sample (
  id CHAR(32) NOT NULL COMMENT '系统分配的标注样本ID',
  project_id CHAR(32) NOT NULL COMMENT '所属标注项目ID',
  fingerprint CHAR(64) NOT NULL COMMENT '排序后附件SHA256集合的摘要，用于项目内同材料组去重',
  creator_id VARCHAR(20) NOT NULL COMMENT '导入样本的中台账号ID',
  assignee_id VARCHAR(20) NOT NULL COMMENT '当前获指派进行标注的中台账号ID',
  status VARCHAR(12) NOT NULL COMMENT 'draft草稿、submitted待复核、returned退回、approved已确认',
  version_no INT UNSIGNED NOT NULL COMMENT '样本的并发版本，每次成功保存或流转递增',
  updated_at DATETIME NOT NULL COMMENT '最近一次成功更新时刻，亚洲上海业务时间',
  name VARCHAR(255) NOT NULL COMMENT '原始文件名或材料组显示名称',
  title VARCHAR(200) NOT NULL COMMENT '人工确认标题，空串表示待填写',
  platform VARCHAR(100) NOT NULL COMMENT '人工记录的材料来源平台，空串表示待填写',
  source_task_id CHAR(32) NULL COMMENT '来源ADM解析来件ID，NULL表示独立文件导入',
  expected SMALLINT UNSIGNED NULL COMMENT '人工指定的预期独立字段证据位置数，NULL表示未设置',
  position_count SMALLINT UNSIGNED NOT NULL COMMENT '服务端按独立来源位置去重后的已标位置数',
  payload LONGTEXT NOT NULL COMMENT '文件索引、字段标记、标题证据、文件标签和复核信息的JSON',
  segments LONGTEXT NOT NULL COMMENT '原文段落及页码或行列位置JSON，样本建立时固定',
  PRIMARY KEY (id),
  UNIQUE KEY uk_annotation_sample_fingerprint (project_id,fingerprint),
  KEY idx_annotation_sample_status (project_id,status,updated_at,id),
  KEY idx_annotation_sample_assignee (project_id,assignee_id,status,updated_at,id),
  CONSTRAINT fk_annotation_sample_project FOREIGN KEY (project_id) REFERENCES annotation_project(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标注样本当前稿，每项目内每组原件一行';

CREATE TABLE IF NOT EXISTS annotation_revision (
  sample_id CHAR(32) NOT NULL COMMENT '所属标注样本ID',
  version_no INT UNSIGNED NOT NULL COMMENT '本次操作形成的样本版本号',
  action VARCHAR(12) NOT NULL COMMENT '导入import、提交submit、确认approve、退回return、指派assign',
  actor_id VARCHAR(20) NOT NULL COMMENT '作出本次操作的中台账号ID',
  occurred_at DATETIME NOT NULL COMMENT '操作成功时刻，亚洲上海业务时间',
  note VARCHAR(500) NOT NULL COMMENT '复核说明或操作备注，空串表示无说明',
  snapshot LONGTEXT NOT NULL COMMENT '操作时固化的证据、标签定义或分配内容JSON',
  PRIMARY KEY (sample_id,version_no),
  CONSTRAINT fk_annotation_revision_sample FOREIGN KEY (sample_id) REFERENCES annotation_sample(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标注主要状态流转审计，每次操作一行';

CREATE TABLE IF NOT EXISTS annotation_dataset (
  id CHAR(32) NOT NULL COMMENT '系统分配的数据集发布ID',
  project_id CHAR(32) NOT NULL COMMENT '所属标注项目ID',
  name VARCHAR(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '项目内唯一的发布名称',
  created_at DATETIME NOT NULL COMMENT '发布成功时刻，亚洲上海业务时间',
  creator_id VARCHAR(20) NOT NULL COMMENT '执行发布的中台账号ID',
  sample_count SMALLINT UNSIGNED NOT NULL COMMENT '发布版本中包含的已确认样本数',
  payload LONGTEXT NOT NULL COMMENT '不可变项目、人工预期、证据及样本版本快照JSON',
  PRIMARY KEY (id),
  UNIQUE KEY uk_annotation_dataset_name (project_id,name),
  CONSTRAINT fk_annotation_dataset_project FOREIGN KEY (project_id) REFERENCES annotation_project(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='已发布的标注样本集，每发布版本一行';
