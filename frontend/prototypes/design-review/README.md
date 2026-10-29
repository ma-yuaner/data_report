# 产品需求与设计工作台

维护源为registry.json；不要手工编辑generated.ts、接口摘录和生成文档。新增需求先登记用户来源、状态、未决规则，再关联页面、字段、接口和数据表。已有代码、候选设计、数据可用性、实现、部署、验收分开。

运行仓库既有命令`npm --prefix frontend run package:product-review`即可生成并打包。generate.mjs核对稳定编号引用，生成工作台数据、Markdown/HTML与OpenAPI公共字段摘录；该摘录不是完整后端schema。关系检查通过不证明业务或真实数据库正确。

DesignExplorer.vue提供搜索、编号跳转、原页面入口、设计包下载及场景入口。runtime.ts只改变资源治理本机响应，不运行真实控制。当前GDS六项需求具备设计链路，ADM仅保留既有组件PRD；不宣称其他模块已覆盖。

布局直接引用原AppLayout，编译替换与适配均在原型配置内。完整结构、边界和扩展约定见docs/development/product-review-architecture.md。没有独立软链接知识库或在线多人共享存储。
