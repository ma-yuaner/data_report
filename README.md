# 企业数据中心 MVP

面向机票业务的独立数据中心。经营总览第一版支持从 Hive 汇总出票、退票、改签、增值利润；指标属于业务估算，不作为正式财务结算口径。

## MVP菜单

- 经营总览：从销售、出票、利润和风险查看经营状态；
- 业务分析：利润分析、售前政策、出票履约、售后退改、结算资金、增值服务；
- 异常工作台：经营、履约、风险和数据异常；
- 数据资产：数据覆盖、指标口径和更新状态。

页面中的平台、航司、供应商、人员、PCC等属于筛选和下钻维度，不作为一级菜单。

## 技术结构

```text
浏览器
  -> Nginx / Vue 3 + TypeScript + ECharts
  -> Flask API
  -> 当前：Mock数据服务
  -> 后续：分析数据集、缓存和权限服务
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

经营总览默认使用演示模式。接入 Hive 时，在 `.env` 中设置 `DATA_MODE=hive`，并填写 `HIVE_HOST`、`HIVE_USER` 等连接信息。连接密码只能保存在部署环境的 `.env`，不得提交到 Git。

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
