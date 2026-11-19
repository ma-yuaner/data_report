# T43 main 一键更新与回退

任务 T43-DEPLOY-20261118。用户授权把部署脚本及审查清单提交公司 GitLab `analytics/data_report` 的 main；不操作 T43，不执行历史任务、不修改历史状态、不发邮件。本次无 SQL、DDL、数据库迁移或数据卷恢复。

## 路径与职责

| 路径 | 内容与维护方式 |
|---|---|
| `/data/data_report` | 现有服务器配置，保留 `.env`、主 Compose、HR Compose、`docker-compose.t43.yml`；不要在这里 `git reset`、覆盖解压或初始化仓库 |
| `/data/data_report-source` | 新的 Git main 检出目录，只用于获取版本化脚本；不放 `.env` 或生产数据 |
| `scripts/deploy/t43/update-t43.sh` | Bash 更新入口，默认 `--check`，不隐式执行更新 |
| `scripts/deploy/t43/update-t43-helper.py` | 隔离 Python 校验器，不导入应用、无网络 |
| `scripts/deploy/t43/build-args.t43.yml` | T43 构建参数覆盖，默认国内 HTTPS pip 源，可由服务器 `.env` 覆盖 |
| `scripts/deploy/t43/reviewed-backend.json` | 已复核后端文件的 SHA256 清单；和代码一起提交，无凭据或业务明细 |
| `/data/data_report-updates/repository.git` | 更新脚本的 main 拉取缓存 |
| `/data/data_report-updates/releases/<时间-提交-PID>` | 每次更新的源码、构建版本、私密运行配置和前一版本快照 |
| `/data/data_report-updates/active.json`、`rollback.json` | 当前/回退运行配置；含凭据，仅 root 访问，禁止上传聊天或提交 Git |

脚本使用已在 T43 导入的 API 镜像 ID `sha256:50f644a6a0338ec01b82d9d7586807a180c2183f0fd1820a96e3eda181dd0ec3` 运行 Python 检查器；请保留该镜像。检查器统一显式使用 UID/GID 0:0 读取 root 私有版本目录，同时保持无网络、只读容器和只读宿主挂载。它只运行校验器，不启动 Flask，也不访问数据库；应用容器仍沿用 Dockerfile 的非 root 用户。不得通过放宽 `.env`、版本目录或快照权限解决校验器访问问题。

## 首次接入与后续命令

以下是完整操作参考，当前迁移仍按用户要求一次执行一步。不要一次复制全部命令。

首次在 T43 获取脚本：

```bash
git clone --branch main --single-branch https://git.ndccloud.com/analytics/data_report.git /data/data_report-source
```

只检查环境、配置与现有卷（不拉代码、不构建、不重启服务）：

```bash
bash /data/data_report-source/scripts/deploy/t43/update-t43.sh --check
```

以后获取最新脚本并更新应用的一条命令：

```bash
git -C /data/data_report-source pull --ff-only origin main && bash /data/data_report-source/scripts/deploy/t43/update-t43.sh --update
```

只拉取不会部署。更新使用脚本再次 fetch 得到的 main 的确切提交，记录完整 SHA；如果两次拉取之间 main 前进，以脚本记录的提交为实际候选。脚本从**同一候选提交**读取后端清单，而非沿用服务器上传的旧清单。清单不匹配时停止，不自动生成或放宽清单。

应用回退：

```bash
bash /data/data_report-source/scripts/deploy/t43/update-t43.sh --rollback
```

回退只恢复前一版本的 API/web 镜像、环境和运行配置，不恢复或倒退 MySQL/SQLite/附件卷，不承诺撤销已经发生的业务写入。发布失败仅尝试回退一次；更新仍返回非零，回退失败必须停下核对，不能反复重跑。

## 更新顺序与保护

1. 核对 T43 主机名、root、Git/Docker/curl/flock、`/data` 挂载、Docker 存储目录、root 600 `.env`、7 个既有卷以及运行容器白名单。发现独立 worker 运行时拒绝更新，不擅自停止其他服务。
2. 读取服务器 `.env` 和安全覆盖配置，不 `source .env`、不回显展开的环境；校验默认服务仅 API/web，邮件、外部投递、自动认证建表为 false，bootstrap 为空，认证启用，Hive 为已核实私网 `172.16.2.217`。
3. 在独立缓存 fetch main，按确切 SHA 导出源码（固定 LF），拒绝仓库跟踪 `.env`。不覆盖现有配置目录，不使用 `git reset --hard`。
4. 从候选源码读取版本化后端清单，比对 backend 全部文件（含 Dockerfile、依赖及任务代码），拒绝符号链接。未复核后端变化停在此处，当前服务不切换。前端及依赖/构建脚本仍是受信任 main 的可执行代码，不是沙箱审计器。
5. 顺序构建 API/web，构建失败时当前容器不切换；构建可能访问软件源，耗时和成功率须在 T43 验证。无关 worker 不构建、不启动。
6. 用新镜像的不可变 ID 生成仅含 API/web 的运行配置，7 个卷及现有 `data_report_default` 网络设为 external；不创建新业务卷替代旧卷。校验端口 1818/5160、挂载、健康命令及禁止自定义入口/命令、生命周期钩子、privileged 等变化。
7. 从运行容器记录上一版实际镜像 ID 和实际环境（不假定当前 `.env` 与旧容器一致），保存 root 私密回退文件。
8. 只对 `api web` 执行 `up --no-deps --no-build --pull never --wait`，随后只访问本机 `/` 与 `/api/health`。失败尝试前一应用版本，不执行业务接口、历史队列清理、发信、DDL、`down`、`prune` 或删除数据卷。

原服务器 `docker-compose.t43.yml` 仍须保留，将五个独立 worker 放入 `manual-workers` profile；脚本生成的运行描述进一步只包含 API/web。不要绕过脚本使用 `--profile '*' up`。`HR_MAIL_SEND_ENABLED=false` 本身不能阻止邮件 worker 改历史状态，`ADM_EXTERNAL_DELIVERY_ENABLED=false` 也不能阻止 ADM worker 推进追偿状态，所以不启动 worker 是独立保护。

## 审查清单维护

初始后端清单源自 `7fd374e0f1ae838167b9b18959789ae821cdf14c`。当前清单已核对后续 main 至 `fcf219e` 的后端增量（投放机会显式编辑及舱位输入归一）及本次 Dockerfile pip 构建参数；共 194 个受控文件。API工厂、认证初始化及 worker/导出/核查自动执行代码未改变；这是部署启动边界审查，不冒充投放功能业务复验。清单中的 commit 是源码复核基线，reviewed_changes注明同批Dockerfile增量，不需要写成包含清单自身的提交，避免自引用。

后续 backend 变化必须先复核启动入口、导入副作用、认证初始化、所有自动恢复/领取/通知路径，再更新清单并与实现同批提交 main。禁止在 T43 对任意新 main 盲目重算清单来绕过保护。维护者可使用 Git LF archive 的文件内容计算 SHA256；Windows 工作区 CRLF 不能直接作为 Linux 清单依据。仓库清单只证明文件匹配已审版本，不是普遍的安全或业务正确性证明。

## pip 下载加速

Docker Hub镜像代理只影响FROM基础镜像，不会加速容器内的pip下载。T43版本化构建覆盖默认使用 `https://pypi.tuna.tsinghua.edu.cn/simple`；该域名和 `/simple` 用法见[清华镜像官方帮助](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)，`--index-url` 见[pip官方安装参数](https://pip.pypa.io/en/stable/cli/pip_install/)。实际T43连通性/下载速度须实测，不承诺耗时。

更新脚本通过Compose读取服务器 `.env` 中可选的 `PIP_INDEX_URL`、`PIP_TIMEOUT`（默认60秒）和 `PIP_RETRIES`（默认3）；分别允许HTTPS、无账号密码/查询串/片段且以 `/simple` 结尾的索引，超时5–300秒、重试0–10次。索引可改为经确认的其他国内源或官方源。地址不允许放凭据，私有认证源须另行设计Secret接入。

这些仅是API构建参数；两条pip命令（升级pip、安装requirements）均显式传入同一索引/超时/重试，`--isolated` 避免隐式用户配置影响，`--no-cache-dir` 保留原无下载缓存策略。不使用HTTP、不加trusted-host、不关闭TLS，不配置额外索引，不写宿主机或镜像的pip.conf，不修改运行容器环境，也不重启Docker。普通直接docker build默认仍用官方PyPI；T43由build-args.t43.yml覆盖为国内源，不改247服务配置。

首次切换pip构建参数会重建依赖安装层；下载完成的镜像层随后可按Docker缓存规则复用。保留requirements原有版本约束，不借加速修改或锁定依赖版本。构建可占用CPU/内存/网络，但构建阶段不停止现有API/web；源码及健康检查通过后才进入已授权的容器切换。

## 当前证据与未验

主会话执行实现与自检，未委派独立代理。L4按生产控制风险保留失败、回退、配置/卷及任务边界检查；本轮只提交脚本，没有独立审查或远端生产演练，不称生产交付完成。

用户回执证明此前迁移包版本的 T43 API/web 为 healthy，公网首页及 `/api/health` 返回 HTTP 200；没有独立 worker 启动。此前服务器检查通过的是上传版脚本，不能替代本次仓库版更新、构建和回退实测。仓库版的本地检查结果见本任务工作流记录；Git 认证、软件源/构建网络、新版本更新及回退仍待 T43 逐步验证。不运行、不等待 CI，不发送发版或测试消息。

复盘：把脚本和后端清单纳入同一个 main，避免“拉到新源码、仍使用服务器旧清单”的版本错配；服务器配置与脚本检出分开，避免迁移目录误用 `git pull`。本次为项目部署入口完善，通用方法已有受控执行规范覆盖，不新增 MYE 方法。
