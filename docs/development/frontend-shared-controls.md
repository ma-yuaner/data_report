# 中台公共控件：开发调用入口

2026-10-24。已实现首轮公共控件与样板接入，不表示所有历史页面已完成迁移。视觉/交互依据见[统一规范](../product/ui-consistency-standard.md)。

## 已有组件如何复用

| 组件 | 职责 | 已接入 |
|---|---|---|
| `PageHeader.vue` | 页标题、说明、主操作插槽 | 沿用既有页面，不另造标题组件 |
| `FilterPanel.vue` | 筛选标签/网格/操作/说明；新增stacked布局及header/period/footer插槽 | 综合分析接入；原GDS航线调用保持兼容 |
| `FormDialog.vue` | 统一窗口宽度/窄屏/内容滚动/保存取消/脏数据确认/忙碌拦截/错误 | ADM新建、引用新建、编辑主单 |
| `FormGrid.vue` | 两列/窄屏一列/通栏字段/控件宽度 | ADM主单、初始订单、明细表单 |
| `DateField.vue` | 中文AntD日期/日期时间，日历字符串，不进行隐式时区转换 | ADM下发日期、处理截止、编码恢复时限；综合分析日期 |
| `DateRangeField.vue` | 两个统一日期控件、起止标签/清空/禁用和change事件 | 综合分析统计期间 |

组件均在`frontend/src/components/`，由页面显式import；没有新依赖、全局业务权限或自动API调用。

## 关键调用契约

- `FormDialog`：`v-model:open`、`title`、`busy`、`dirty`、`error`、`submitDisabled`、`@submit`。默认保存/取消，宽800px，遮罩不关闭。页面掌管草稿、校验、幂等键、API及成功关闭；组件不会自行宣告成功或丢弃失败输入。`dirty`由初始化快照比较，成功后更新基线。取消变更需确认，忙碌时关闭/重复提交被拦截。
- `FormGrid`：默认插槽放字段；每字段一label，必填星号与文字放同一span；通栏加`form-span`（兼容已有`adm-span`）。只管布局，不做业务校验。
- `DateField`：默认`v-model`字符串；日期`YYYY-MM-DD`，`with-time`为`YYYY-MM-DDTHH:mm`。`allow-clear`默认true，清空输出空字符串；`disabled`、`placeholder`、`aria-label`由调用方指定。北京时间说明和格式化仍按业务契约，不能用Date/UTC转换悄悄改业务时刻。
- `DateRangeField`：`v-model:start`、`v-model:end`字符串，`label`、`disabled`、`allow-clear`（默认false），`@change`只通知修改、不自动请求。快捷日期、最大范围、起止校验、是否包含结束日由页面保留，组件不猜统计规则。
- `FilterPanel`：已有默认调用不变；复杂页用`stacked`，把快捷时间放period、标题放header、数据缺口放footer。`instant=false`明确手动查询；`hint`可显示待应用状态；自带重置可用`loading`禁用，自定义操作时`show-reset=false`避免双按钮。页面管理查询快照和请求，不输入即重查。
- 人员/字典当前继续复用AntD Select与各业务权限API；不做一个跨模块拿全员的通用接口。不要把本次组件清单说成已经统一所有人员选择器、表格或抽屉。

## 验证与后续迁移

首轮针对组件状态/日期事件/插槽兼容、类型、相关ESLint、组件注册和生产构建验证。浏览器被Work设置禁用，真实布局、缩放、弹窗焦点及中文输入尚未实操，不能宣称全站或247验收通过。测试脚本只留忽略目录。

人工验收：ADM打开→输入→选日期/时间→加两条订单→取消确认/继续编辑→保存失败保草稿→保存成功刷新；综合分析改日期/维度不立即请求→查询→重置→原GDS筛选仍可用；1280/1024宽、低高度和125%缩放看底部按钮/日期弹层是否可达。

后续触及页面优先替换相同组合，不批量机械改业务；原生日期与业务时区、特殊表单的联动规则先核对。未接入页面列明，不靠全局CSS强制覆盖成“已统一”。
