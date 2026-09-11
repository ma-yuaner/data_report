# 企业数据中心 MVP

面向机票业务的独立数据中心。当前版本只提供可运行的平台框架、演示数据和页面编排，不连接生产数据库，也不作为正式经营或财务口径。

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

访问 `http://127.0.0.1:5173`，Vite会将 `/api` 代理至 `http://127.0.0.1:5050`。

## Docker启动

```powershell
docker compose up -d --build
```

访问：

- 数据中心：`http://127.0.0.1:8080`
- 后端健康检查：`http://127.0.0.1:5050/api/health`

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

