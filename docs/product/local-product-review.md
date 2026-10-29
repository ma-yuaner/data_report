# 本地产品评审台：使用与开发交接

门户版本0.1、ADM原型版本0.4，2026-10-29。用户最新要求直接复用原前端页面，按实际弹窗/抽屉/页签操作并联动组件PRD，开发完成由用户自行测试；未定规则及原方案与旧组件的差异明确记录，正式接口与部署仍独立授权。

## 业务人员怎么打开

当前工作区双击 `D:\data_center_code\产品评审台_打开我.html`，使用Chrome/Edge打开。入口跳转到同目录 `产品评审台/index.html`，不需要登录或启动后端。选择ADM可在新窗口打开现有DEMO；其他模块仅登记目录，明确标为待接入。

ADM需求可以在“ADM需求整理”页面填写、保存本机、导出TXT和JSON草稿备份。JSON可以恢复并会确认替换；缓存失败显示提示，导出文件应自行保留。导出仅发起浏览器下载，不代表上传或共享，下载内容不进入Git。草稿不是业务确认，也不是批准。

也可使用Word/Excel/会议纪要，不强制模板。放入 `D:\data_center_code\产品评审资料\ADM`，告诉代理路径、最新版本和本次需要处理的范围。资料目录在仓库外；无真实数据自动扫描、上传或同步。需求整理模板由打包脚本首次复制，再次打包不覆盖填写内容。

## 同事拉取后如何复现

1. 拉取data_report的main，在仓库根目录执行 `npm --prefix frontend ci`（缺少依赖时）。
2. 执行 `npm --prefix frontend run package:product-review`。
3. 脚本在仓库的上级目录生成“产品评审台_打开我.html”、“产品评审台”目录和“产品评审资料/ADM”目录。不同检出路径下以自己的仓库上级目录为准。
4. 双击入口文件。分享已构建的原型时，把完整“产品评审台”目录发给对方，对方打开index.html；单独发首页会缺少ADM链接目标。

包内只有自包含静态HTML，无后端、API代理和账号目录。正式前端1818/5160及路由不受影响。Git只提交源码、构建入口、模板和交接文档；生成HTML及原始资料保存在仓库外。

ADM 0.3默认原ADM管理→我的工作台与连续办理，包内另含`ADM管理PRD_0.3.html`。2026-10-29按用户要求保留原中台完整菜单：`generate-system-navigation.mjs`从正式`src/layouts/AppLayout.vue`读取层级/名称/顺序/预留状态，生成`system-navigation.ts`供ADM与门户目录使用；不加载正式认证或接口。其他模块仅展示原位置及接入说明。ADM内六组仅是页面/窗口评审索引，不另建系统一级菜单，公共账号、通知和导出优先复用；接入状态在PRD单列。字段/按钮说明的唯一来源为`frontend/prototypes/adm-review/product-spec.ts`，`generate-prd.mjs`同步生成仓库PRD和可阅读HTML。所有原型业务状态和本机文件只存浏览器，缓存不足须导出备份；旧0.2缓存和批准不自动迁移。

## 固定文件职责

0.4入口为`frontend/prototypes/adm-review/live/LiveApp.vue`。`main.ts`直接引用正式ADM视图；`vite.adm-prototype.config.ts`只在原型构建将HTTP/账号/导出store切换到本机适配层。`live/contract-tools.mjs`在构建时给正式组件的编译副本添加PRD标识和左舞台图层容器，不修改正式源文件；`live/generate-contract.mjs`同步生成组件定义及0.4 PRD。`live/semantics.ts`维护业务含义。正式页面升级后重建原型即可继承结构，PRD含义仍需人工复核。

当前门户打开`ADM产品验收台_DEMO_0.4.html`，完整文档为`ADM管理PRD_0.4.html`；0.4业务和组件意见通过顶部备份导出/恢复，缓存与0.3独立。原0.3源码仍保留供方案对照，不自动把其新增功能等同于已在正式组件实现。

| 位置 | 维护内容 |
| --- | --- |
| frontend/prototypes/product-review/catalog.ts | 模块注册、状态、相对HTML入口、源码与文档索引，需求整理提示 |
| frontend/prototypes/product-review/App.vue | 门户及本机需求草稿，不导入认证业务页面 |
| frontend/prototypes/shared | PRD面板、工具栏、分栏、公共样式、离线构建器 |
| frontend/prototypes/adm-review | ADM合成原型、现有场景和PRD，待本次需求评审后迭代 |
| docs/product/modules/adm/README.md | ADM需求来源、台账、待确认项及正式开发交接入口 |
| docs/product/modules/adm/requirements.md | 初始需求索引；接收线下资料后逐条补齐规则与验收 |

## 复用和一致性边界

本轮复用中台Ant Design Vue Layout/Menu、PageHeader及main.css，复用已抽取PrdPanel/PanelDivider。正式AppLayout包含身份、路由和权限接口，不直接加载。模块页与正式系统共享展示组件的改造尚待逐个模块实施；前端技术相同不代表原型等于真实业务实现。

新增模块先查看catalog和相关文档，再查现有页面/组件。不复制ADM的权限、财务状态或批准逻辑。按需求编号关联页面、业务规则和验收；更新受影响文件，不重新生成全部文档。需要开发共享展示组件时，由模拟数据入口和正式接口入口分别驱动，权限仍由后端控制。

用户原始资料先保留来源，代理整理脱敏后的需求基线再提交Git；已确认、待确认、产品建议、暂不实施必须区分。涉及旧系统能力需要定向核对，不把未检查过的代码标成已可复用。

## 验证范围

构建包含两个原型各自类型检查及离线打包。离线产物检查覆盖脚本后置、无外部入口与语法，需求草稿检查覆盖字段/长度与文本导出。浏览器真实下载、缓存、拖拽、窄屏、缩放及新窗口行为需实际验收，静态检查不能代替。

## 资源治理现状基线0.1（2026-10-29）

门户“资源治理”打开`资源治理原页面评审_DEMO_0.1.html`，默认GDS资源治理。原六个菜单、分析抽屉、图表及治理演示组件直接复用，与ADM处于同一个实际菜单壳；`资源治理PRD_0.1.html`是可独立阅读的152项组件说明。详见[模块固定入口](modules/resource-governance/README.md)。

源码适配与PRD生成位于`frontend/prototypes/resource-review`，仍使用上面的同一条打包命令。原型API别名只返回本机合成样例，导出仅生成本机CSV；原治理事件/任务使用独立缓存，并纳入顶部备份。正式组件、后端、ETL及生产不变。本版等待用户新需求，不把旧演示参数、技术回执或治理效果视为正式业务确认。
