# 企业数据中心 MVP

面向机票业务的独立数据中心。经营总览第一版支持从 Hive 汇总出票、退票、改签、增值利润；指标属于业务估算，不作为正式财务结算口径。

## MVP菜单

- 经营总览：统一查看出、退、改、增利润及总预估利润；
- 业务分析：出票、退票、改签、增值四个实际数据入口；
- 数据资产：四张核心业务表、当前指标口径和最新数据时间。

尚无可靠数据支撑的全链路、异常工作台和明细查询暂不放入菜单。平台、航司、供应商、人员、PCC等属于筛选和下钻维度，不作为一级菜单。

## 技术结构

```text
浏览器
  -> Nginx / Vue 3 + TypeScript + ECharts
  -> Flask API
  -> 当前：Hive业务宽表（5分钟查询缓存）
  -> 后续：MySQL ADS / Hive按数据量分层，API结构保持稳定
```

## 本地开发

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe app.py
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`，Vite会将 `/api` 代理至 `http://127.0.0.1:5160`。

## Docker启动

```powershell
docker compose up -d --build
```

访问：

- 数据中心：`http://127.0.0.1:1818`
- 后端健康检查：`http://127.0.0.1:5160/api/health`

经营总览提供今日、昨日、本月、本年和自定义日期查询，默认展示本年累计。项目默认使用演示模式；接入 Hive 时，在 `.env` 中设置 `DATA_MODE=hive`，并填写 `HIVE_HOST`、`HIVE_USER` 等连接信息。连接密码只能保存在部署环境的 `.env`，不得提交到 Git。

“业务分析 → 出票分析”提供利润和业务量趋势、平台/航司/供应商/组织贡献，以及首批 12 个分析字段的非空率体检。退票、改签和增值分析首版只展示数量、利润、单笔利润、负利润记录和趋势，避免在问题尚未明确时堆叠无效维度。

“数据资产”直接展示四张实际 Hive 业务表、字段数、已登记指标、业务条件和最新业务时间；未来日期等明显质量问题会显示为异常。

## 当前核心接口

- `GET /api/v1/dashboard/overview`：出退改增经营总览；
- `GET /api/v1/analysis/issue-profit`：出票利润与维度分析；
- `GET /api/v1/analysis/business-profit/{refund|change|ancillary}`：退改增统一分析契约；
- `GET /api/v1/assets/catalog`：核心表、指标和更新状态。

## 验证

```powershell
cd backend
python -m pytest -q

cd ..\frontend
npm run type-check
npm run build
```

## 数据接入原则

- 未接入的数据展示“待接入”，不能展示为0；
- 未确认的指标展示“口径待确认”，不能作为正式KPI；
- 所有金额区分预期、业务估算和已结算；
- 生产数据通过只读账号和指标查询服务接入；
- 演示数据带有明确的 `mock` 标识。
