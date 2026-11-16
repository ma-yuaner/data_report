-- 数据资产业务字典：应用私有SQLite文件，不执行在ERP/MySQL/Hive。
-- SQLite不支持COMMENT元数据；中文字段字典见docs/development/data-assets-implementation-20261116.md。
-- 草稿：每个资产一条可变草稿，revision用于乐观并发，base_revision防止基于旧发布版本覆盖。
CREATE TABLE IF NOT EXISTS asset_dictionary_draft (
  asset_id TEXT PRIMARY KEY,       -- 连接别名/实例指纹/数据库/表组成的稳定资产身份
  revision INTEGER NOT NULL,      -- 本条草稿修订号，从1递增；发布后草稿被移除
  base_revision INTEGER NOT NULL, -- 草稿依据的已发布字典修订号；0表示尚未发布
  body TEXT NOT NULL,             -- JSON业务字典正文，八个已知文本字段；空字符串表示待维护
  snapshot_version TEXT NOT NULL, -- 保存草稿所依据的结构快照SHA-256
  updated_at TEXT NOT NULL,       -- 应用业务时区时间，含时区偏移
  updated_by TEXT NOT NULL        -- 服务端认证账号ID，不接收客户端指定操作人
);
-- 发布修订：每个资产每次发布一条不可覆盖历史；读当前值取该资产最大revision。
CREATE TABLE IF NOT EXISTS asset_dictionary_revision (
  asset_id TEXT NOT NULL,         -- 同草稿稳定身份，关联文件快照而非数据库外键
  revision INTEGER NOT NULL,      -- 发布修订号，从1递增
  body TEXT NOT NULL,             -- 发布时草稿正文JSON，不从物理注释自动填充
  snapshot_version TEXT NOT NULL, -- 发布核对的结构快照SHA-256
  updated_at TEXT NOT NULL,       -- 发布时间，含业务时区偏移
  updated_by TEXT NOT NULL,       -- 服务端认证发布账号ID
  PRIMARY KEY(asset_id, revision)
);
