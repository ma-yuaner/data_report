# 数据资产设计评审 0.1

仅离线评审，不改正式AssetsView、不调用API、不连接数据库。原型复用PageHeader、PrdPanel、PanelDivider和shared/offline-build，使用项目Ant Design Vue与main.css。

设计规则：docs/product/data-assets-design-v01.md；结构化联动规则definition.ts；搜索与图遍历model.ts。真实盘点快照在打包时从工作区受控目录注入，禁止将原始CSV/元数据复制进本源码目录或提交。

入口构建配置：frontend/vite.asset-review.config.ts。类型检查：`node node_modules/vue-tsc/bin/vue-tsc.js -p prototypes/asset-review/tsconfig.json --noEmit`。构建使用项目已验证的bundled Python subprocess调用Node/Vite路径，避免已知PowerShell包装故障。

页面编辑与角色是本地演练；草稿只在内存中，关闭丢失，支持导出评审意见。失败演练不发请求，也不修改采集时间、计数或原快照。权限需正式后端实现，原型不证明鉴权。
