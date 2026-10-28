<template>
  <div class="review-app" :class="{ 'doc-only': docOnly, 'sim-only': simOnly }">
    <ReviewToolbar
      v-model:show-docs="showDocs"
      title="ADM 管理 · 原型与 PRD"
      :version="VERSION"
      status="可直接操作"
      :can-detach="!docOnly"
      @export="downloadReview"
      @import="restoreFile"
      @detach="detach"
    />
    <div class="sandbox">
      本地前端原型 · 数据与文件保存在本机 · 外部订单、通知及汇率使用模拟数据
      <span>演练时钟：{{ state.clock.replace('T', ' ') }}</span>
    </div>
    <div v-if="notice" class="feedback" role="status">
      {{ notice }}<button @click="notice = ''" aria-label="关闭提示">×</button>
    </div>
    <div class="workspace" :style="{ '--sim-width': split + '%' }">
      <section v-if="!docOnly" class="simulation" aria-label="左侧模拟系统">
        <div class="sim-header">
          <strong>左侧 · 模拟系统</strong
          ><label
            >当前模拟人员
            <a-select
              aria-label="当前模拟人员"
              :value="actor"
              :options="roles.map((item) => ({ value: item.id, label: item.name }))"
              @change="changeActor"
          /></label>
        </div>
        <div class="sim-body">
          <nav class="sidebar" aria-label="模拟系统菜单">
            <span class="nav-caption">任务到人 · 中台办理</span
            ><button
              v-for="menu in menus"
              :key="menu.id"
              :class="{ active: page === menu.id }"
              @click="navigate(menu.id)"
            >
              {{ menu.title }}<small>{{ menu.sub }}</small>
            </button>
            <button @click="showAdvanced = !showAdvanced">
              {{ showAdvanced ? '收起辅助工具' : '旧演练与评审记录' }}
            </button>
            <div class="role-purpose">
              {{ roles.find((item) => item.id === actor)?.purpose }}
              <p>仅为原型角色切换；正式身份与权限由后台控制。</p>
            </div>
          </nav>
          <main class="sim-content">
            <OperationsDesk
              v-if="deskPages.includes(page)"
              :state="state"
              :actor="actor"
              :page="page"
              @update="state = $event"
              @open="openCase"
              @create="openIntake()"
              @role="changeDeskRole"
              @notice="openNotice"
              @navigate="navigate"
            />
            <template v-else-if="page === 'overview'">
              <p class="eyebrow">先体验，再定规则</p>
              <h1>把工作送到人，而不是让人找单。</h1>
              <p class="lead">一张供应 ADM，多笔出退改订单。每个人只看到需要自己处理的事项，做完自动进入下一步。</p>
              <div class="steps-strip">
                <span>① 选择案例</span><span>② 按提示切换角色</span><span>③ 办理每项任务</span
                ><span>④ 右侧提意见 / 验收</span>
              </div>
              <h2>选一条路线，开始体验</h2>
              <div class="scenario-grid">
                <article v-for="scenario in scenarios" :key="scenario.id">
                  <h3>{{ scenario.title }}</h3>
                  <p>{{ scenario.description }}</p>
                  <button class="primary" @click="startScenario(scenario.id)">开始这条演练 →</button>
                </article>
              </div>
              <h2>业务全景与功能去向</h2>
              <div class="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>功能板块</th>
                      <th>这次原型怎么体现</th>
                      <th>迁移取舍</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in landscape" :key="item[0]">
                      <td>{{ item[0] }}</td>
                      <td>{{ item[1] }}</td>
                      <td>{{ item[2] }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="callout">
                建议先走“正常办理”，再验证异常。不是所有待确认规则都已经定案：右侧“待确认”可以逐项留下意见。全部资料均是合成示例，请不要输入真实客户、票号或凭据。
              </div>
            </template>
            <template v-else-if="page === 'work' || page === 'dispatch'">
              <div class="section-heading">
                <div>
                  <h1>{{ page === 'work' ? '我的工作' : '团队调度' }}</h1>
                  <p>
                    {{
                      page === 'work'
                        ? '只呈现当前模拟人员需要处理的事项。点任务，直接进入办理步骤。'
                        : '异常归协调人，不随机分派。协调人可以查看团队负荷与接收异常。'
                    }}
                  </p>
                </div>
                <div class="toolbar">
                  <button v-if="actor === 'lead'" @click="navigate(page === 'dispatch' ? 'work' : 'dispatch')">
                    我的待办 / 本组督办</button
                  ><button @click="navigate('ledger')">查看 ADM 台账</button>
                </div>
              </div>
              <div class="metrics">
                <article>
                  <strong>{{ displayTasks.length }}</strong
                  ><span>当前任务（非订单数）</span>
                </article>
                <article>
                  <strong>{{ displayTasks.filter((item) => item.overdue).length }}</strong
                  ><span>超过演练期限</span>
                </article>
                <article>
                  <strong>{{ displayTasks.filter((item) => !item.dueAt).length }}</strong
                  ><span>未设期限，不视为达标</span>
                </article>
              </div>
              <div v-if="page === 'dispatch' && !['coordinator', 'lead'].includes(actor)" class="callout">
                该板块仅协调人可管理。请在上方切换“林协调”，这不会给真实账号授权。
              </div>
              <template v-else
                ><div class="task-list table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>任务 / 单据</th>
                        <th>负责人</th>
                        <th>期限</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="task in displayTasks" :key="task.id">
                        <td>
                          <strong>{{ task.title }}</strong
                          ><small class="table-sub"
                            >{{ state.cases.find((item) => item.id === task.caseId)?.admNo }} · {{ task.kind }}</small
                          >
                        </td>
                        <td>{{ roleName(task.owner) }}</td>
                        <td>
                          <span :class="task.overdue ? 'danger-text' : ''">{{
                            task.dueAt?.replace('T', ' ') || '未设期限'
                          }}</span>
                        </td>
                        <td><button class="primary" @click="openTask(task)">打开办理</button></td>
                      </tr>
                    </tbody>
                  </table>
                  <div v-if="!displayTasks.length" class="empty">
                    当前没有分给你的任务。可以按上方演练提示切换人员；没有任务不代表业务已全部完成。
                  </div>
                </div></template
              >
              <h2>本人提醒收件箱</h2>
              <p class="muted">正式派单通知承办人、组长督办；预罚邮件为准、群辅助。此处模拟通知，不真实发送。</p>
              <article
                v-for="item in state.notices
                  .filter((item) => item.recipient === actor)
                  .slice(-12)
                  .reverse()"
                :key="item.id"
                class="inbox-row"
              >
                <span>{{ item.text }}</span
                ><button @click="openNotice(item)">打开本人处理页</button
                ><button :disabled="item.read" @click="markRead(item.id)">{{ item.read ? '已读' : '标为已读' }}</button>
              </article>
            </template>
            <template v-else-if="page === 'intake'">
              <h1>接收与匹配</h1>
              <p>录入供应原件信息及订单子项，核对金额后派发。预罚单可先核实，后转正式。</p>
              <div v-if="actor !== 'coordinator'" class="empty">仅协调人可接收，当前人员请从“我的工作”办理。</div>
              <template v-else
                ><div class="toolbar">
                  <button class="primary" @click="openIntake()">新建 ADM（单条录入）</button
                  ><button @click="openIntake(true)">复制引用当前供应</button>
                  <button @click="navigate('exchange')">批量导入 / 模板</button>
                </div>
                <p class="muted">
                  结构化填写主单和订单子项；CSV统一模板可批量预览导入。票号识别提供本地候选，仍由录入人确认。
                </p>
                <article v-for="item in state.cases" :key="item.id" class="case-card">
                  <div>
                    <h3>
                      {{ item.admNo }} <span class="badge">{{ caseStatus(item) }}</span>
                    </h3>
                    <p>
                      {{ item.supplier }} · {{ item.lines.length }} 个订单 · {{ item.amount }}
                      {{ item.currency || 'CNY' }}
                    </p>
                    <p>
                      未匹配 {{ item.lines.filter((line) => line.stage === 'MATCH').length }} · 待分派
                      {{ item.lines.filter((line) => line.stage === 'ASSIGN').length }}
                    </p>
                  </div>
                  <button @click="openCase(item.id)">核对接收结果</button>
                </article></template
              >
            </template>
            <template v-else-if="page === 'ledger'">
              <h1>ADM 档案</h1>
              <p>台账用于查询与追溯，不再是日常找工作入口。不同人员只查看与自己有关的订单。</p>
              <label class="search"
                >搜索 ADM、订单、PNR、备注
                <a-input
                  v-model:value="search"
                  placeholder="输入后点击查询"
                  @press-enter="appliedSearch = search" /></label
              ><button @click="appliedSearch = search">查询</button>
              <div v-for="item in visibleCases" :key="item.id" class="case-card">
                <div>
                  <h3>
                    {{ item.admNo }} <span class="badge">{{ caseStatus(item) }}</span>
                  </h3>
                  <p>
                    {{ item.supplier }} · 获权明细 {{ visibleLines(item, actor).length
                    }}<template v-if="actor === 'coordinator'">
                      · {{ item.amount }} {{ item.currency || 'CNY' }}</template
                    >
                  </p>
                  <p>{{ actor === 'coordinator' ? item.remark : '主单金额/备注不向部分明细人员展开' }}</p>
                </div>
                <button class="primary" @click="openCase(item.id)">查看档案 →</button>
              </div>
              <p v-if="!visibleCases.length" class="empty">没有符合当前人员和查询条件的档案。</p>
            </template>
            <template v-else-if="page === 'case' && current">
              <button class="back-link" @click="navigate('work')">← 回到我的工作</button>
              <div class="section-heading">
                <div>
                  <h1>{{ current.admNo }}</h1>
                  <p>{{ current.supplier }} · {{ caseStatus(current) }} · 模拟版本 {{ state.version }}</p>
                </div>
                <div class="toolbar">
                  <button v-if="actor === 'coordinator'" @click="openIntake(true)">复制引用</button
                  ><button v-if="canEditCase(current, actor)" @click="openAction('edit')">编辑基础信息</button
                  ><button v-if="current.preliminary && canEditCase(current, actor)" @click="openAction('preliminary')">
                    预罚转正式
                  </button>
                </div>
              </div>
              <div class="case-summary">
                <span>获权订单 {{ visibleLines(current, actor).length }}</span
                ><span v-if="actor === 'coordinator'"
                  >原件金额 {{ current.amount }} {{ current.currency || 'CNY' }} · 明细分摊 {{ allocated(current) }}
                  {{ current.currency || 'CNY' }}</span
                ><span v-else>部分明细权限：主单金额与其他订单隐藏</span>
              </div>
              <div v-if="current.historyOnly" class="callout">
                历史只读档案 · 保留旧业务事实，未迁移真实附件或财务确认；可以复制引用新建。
                <details>
                  <summary>查看原始历史记录</summary>
                  <pre>{{ current.historySource }}</pre>
                </details>
              </div>
              <div v-if="current.preliminary" class="callout">预罚核实阶段 · 核实后由协调人补齐正式信息并转正式。</div>
              <div class="lifecycle-strip">
                <span v-for="step in ['接收', '办理', '申诉 / 差异', '独立审核', '业务结案', '回款跟进']" :key="step">{{
                  step
                }}</span>
              </div>
              <div class="case-tabs" role="tablist" aria-label="档案功能">
                <button
                  v-for="tab in caseTabs"
                  :key="tab.id"
                  role="tab"
                  :aria-selected="caseTab === tab.id"
                  :class="{ active: caseTab === tab.id }"
                  @click="changeTab(tab.id)"
                >
                  {{ tab.title }}
                </button>
              </div>
              <template v-if="caseTab === 'history'"
                ><h2>完整操作历史（当前获权范围）</h2>
                <article v-for="event in visibleEvents.slice().reverse()" :key="event.id" class="event">
                  <strong>{{ actionNames[event.action] || event.action }}</strong
                  ><span>{{ event.at }} · {{ roleName(event.actor) }} · 第{{ event.round }}轮</span>
                  <p>{{ event.before }} → {{ event.after }}；{{ event.reason }}</p>
                </article>
                <p v-if="!visibleEvents.length" class="empty">
                  尚无模拟操作记录。演练初始资料不是伪造的操作历史。
                </p></template
              >
              <template v-else-if="caseTab === 'attachments'"
                ><h2>原件与证据</h2>
                <p class="muted">
                  可上传本机文件或补充文字，仅保存在当前浏览器。支持图片/PDF/文本预览及下载，主单原件与订单证据分别授权。
                </p>
                <div class="toolbar">
                  <button
                    v-if="
                      !current.historyOnly &&
                      (current.status !== 'CLOSED' ||
                        (actor === current.remediation.owner && current.remediation.status === '整改中'))
                    "
                    @click="openAction('attach')"
                  >
                    上传 / 补充材料
                  </button>
                </div>
                <article v-for="file in readableFiles" :key="file.id" class="attachment">
                  <div>
                    <strong>{{ file.name }}</strong>
                    <p>{{ file.category }} · {{ file.lineId || '主单原件' }} · 共享明细 {{ file.shared.length }}</p>
                    <details>
                      <summary @click="focusDoc('attachments')">预览材料</summary>
                      <img
                        v-if="file.dataUrl && file.mime?.startsWith('image/')"
                        :src="file.dataUrl"
                        :alt="file.name"
                        class="attachment-preview"
                      />
                      <iframe
                        v-else-if="file.dataUrl && file.mime === 'application/pdf'"
                        :src="file.dataUrl"
                        :title="file.name"
                        class="pdf-preview"
                        sandbox=""
                      />
                      <pre v-else>{{ file.content }}</pre>
                    </details>
                  </div>
                  <div class="toolbar">
                    <button @click="downloadAttachment(file)">下载材料</button
                    ><button
                      v-if="actor === 'coordinator' && current.status !== 'CLOSED'"
                      @click="openAction('share', { fileId: file.id, lineIds: [...file.shared] })"
                    >
                      授权 / 撤销共享
                    </button>
                  </div>
                </article></template
              >
              <template v-else-if="caseTab === 'close'"
                ><h2>主单结案检查</h2>
                <p>子订单逐项完成后，还须核对分摊、原件与交接。非必需整改独立跟踪，不自动改写已结案事实。</p>
                <div v-if="current.status === 'CLOSED'" class="callout success">
                  主单已结案，核心事实只读。{{ current.remediation.status }} · {{ roleName(current.remediation.owner) }}
                </div>
                <ul v-else class="check-list">
                  <li v-for="blocker in blockers(current)" :key="blocker">未通过：{{ blocker }}</li>
                  <li v-if="!blockers(current).length" class="good">结案前置检查通过；仍需协调人确认依据。</li>
                </ul>
                <div class="toolbar">
                  <button
                    v-if="actor === 'coordinator' && current.status === 'ACTIVE'"
                    class="primary"
                    @click="openAction('close')"
                  >
                    核对并结案</button
                  ><button
                    v-if="actor === 'coordinator' && !current.historyOnly && current.status === 'CLOSED'"
                    @click="openAction('reopen')"
                  >
                    授权重开（留痕）</button
                  ><button
                    v-if="
                      current.status === 'CLOSED' &&
                      actor === current.remediation.owner &&
                      current.remediation.status === '待整改'
                    "
                    class="primary"
                    @click="openAction('remediation_accept')"
                  >
                    接收整改任务</button
                  ><button
                    v-if="
                      current.status === 'CLOSED' &&
                      actor === current.remediation.owner &&
                      current.remediation.status === '整改中'
                    "
                    class="primary"
                    @click="openAction('remediate')"
                  >
                    提交整改验证结果</button
                  ><button
                    v-if="
                      current.status === 'CLOSED' && actor === 'reviewer' && current.remediation.status === '待复核'
                    "
                    class="primary"
                    @click="openAction('remediation_review')"
                  >
                    独立复核整改
                  </button>
                </div>
                <p v-if="current.remediation.result">整改结果：{{ current.remediation.result }}</p>
                <details v-if="current.closedSnapshots?.length">
                  <summary>查看结案冻结快照（重开后仍保留）</summary>
                  <pre>{{ current.closedSnapshots }}</pre>
                </details></template
              >
              <template v-else>
                <label class="line-selector"
                  >当前订单明细
                  <a-select
                    aria-label="当前订单明细"
                    :value="selectedLine"
                    :options="
                      visibleLines(current, actor).map((line) => ({
                        value: line.id,
                        label: `${line.orderNo || '待匹配'} · ${line.platform} · ${line.business}`,
                      }))
                    "
                    @change="chooseLine"
                /></label>
                <div v-if="!activeLine" class="empty">当前没有获权订单；如为结案后整改，请打开“结案与整改”。</div>
                <template v-else
                  ><div class="stage-heading">
                    <span class="badge">{{ stageNames[activeLine.stage] }}</span
                    ><span
                      >当前承办：{{ roleName(activeLine.owner) }} · 第{{ activeLine.round }}轮 · {{ activeLine.amount }}
                      {{ current.currency || 'CNY' }}</span
                    >
                  </div>
                  <dl class="fields">
                    <div>
                      <dt>订单号 / 票号</dt>
                      <dd>{{ activeLine.orderNo || '待匹配' }} / {{ activeLine.ticketNo }}</dd>
                    </div>
                    <div>
                      <dt>平台 / 细分站点 / PNR</dt>
                      <dd>{{ activeLine.platform }} / {{ activeLine.site }} / {{ activeLine.pnr }}</dd>
                    </div>
                    <div>
                      <dt>差异分类</dt>
                      <dd>{{ activeLine.diffType }} · {{ activeLine.attribution }}</dd>
                    </div>
                    <div>
                      <dt>期限（演练）</dt>
                      <dd>{{ activeLine.dueAt.replace('T', ' ') || '缺失，不视为按时' }}</dd>
                    </div>
                  </dl>
                  <div v-if="current.paused || current.status === 'VOID'" class="callout">
                    {{ current.paused ? '主单已挂起，恢复前不能推进' : '主单已作废，只读保留' }}
                  </div>
                  <div class="actionbar">
                    <button
                      v-for="action in permitted.filter(
                        (value) => !['record', 'collab_create', 'responsibility', 'amount'].includes(value),
                      )"
                      :key="action"
                      :class="{ primary: primaryActions.includes(action) }"
                      @click="openAction(action)"
                    >
                      {{ actionNames[action] }}
                    </button>
                    <p v-if="!permitted.length" class="muted">
                      此角色在当前节点只能查看。按上方演练指引切换下一责任人，不以隐藏按钮代替真实系统鉴权。
                    </p>
                  </div>
                  <div class="toolbar">
                    <button
                      v-for="name in permitted.filter((value) =>
                        ['record', 'collab_create', 'responsibility', 'amount'].includes(value),
                      )"
                      :key="name"
                      @click="openAction(name)"
                    >
                      {{ actionNames[name] }}</button
                    ><button
                      v-if="!current.historyOnly && activeLine.owner === actor && activeLine.stage === 'INVESTIGATE'"
                      @click="openAction('recovery')"
                    >
                      恢复编码</button
                    ><button
                      v-if="
                        !current.historyOnly &&
                        current.status === 'ACTIVE' &&
                        (activeLine.owner === actor || actor === 'coordinator') &&
                        !['REVIEW', 'DONE'].includes(activeLine.stage)
                      "
                      @click="openAction(activeLine.lockedBy ? 'unlock' : 'lock')"
                    >
                      {{ activeLine.lockedBy ? '解除办理锁' : '锁定本人编辑' }}</button
                    ><button @click="changeTab('attachments')">查看 / 补充附件</button>
                  </div>
                  <p v-if="activeLine.lockedBy" class="callout">
                    当前编辑锁：{{ roleName(activeLine.lockedBy) }}。他人持锁时先协调解锁。
                  </p>
                  <div v-if="nextExperienceTask" class="handoff-banner">
                    <span>下一待办：{{ nextExperienceTask.title }} · {{ roleName(nextExperienceTask.owner) }}</span
                    ><button @click="experienceNext">切换下一处理人并打开</button>
                  </div>
                  <section class="detail-section">
                    <h2>ADM内容与处理意见</h2>
                    <p class="prose">{{ activeLine.description }}</p>
                    <p v-if="current.sourceType">
                      {{ current.sourceType }} · 航司 {{ current.airline }} · 回复截止 {{ current.replyDue }} ·
                      人民币参考 {{ current.referenceCny || '未换算' }}
                    </p>
                    <p v-if="activeLine.borneAmount">
                      承担金额：{{ activeLine.borneAmount }} {{ current.currency || 'CNY' }}
                    </p>
                    <dl class="analysis">
                      <div v-for="field in analysisFields" :key="field.key">
                        <dt>{{ field.label }}</dt>
                        <dd class="prose">{{ activeLine[field.key] || '尚未填写' }}</dd>
                      </div>
                    </dl>
                    <p>申诉决策：{{ activeLine.appealDecision }}；{{ activeLine.appealReason || '尚无依据' }}</p>
                    <p>
                      恢复编码：{{
                        activeLine.recoveryRequired
                          ? `${activeLine.recoveryCode || '待补'} / ${activeLine.recoveryResult || '待完成'}`
                          : '未要求（不自动生成48小时SLA）'
                      }}
                    </p>
                    <p>
                      差异登记：{{ activeLine.differenceRecorded ? '已录差异' : '未录差异' }} ·
                      {{ activeLine.differenceReason || '尚无登记或无需登记依据' }}
                    </p>
                    <p>
                      回款：{{
                        !activeLine.financeRequired
                          ? '无需回款'
                          : activeLine.financeReference
                            ? '已回款'
                            : activeLine.stage === 'DONE'
                              ? '业务已审核 · 待回款'
                              : '审核后跟进回款'
                      }}
                      · {{ activeLine.financeReference || activeLine.financeReason || '待补'
                      }}<span v-if="activeLine.settledAmount">
                        · 凭证金额 {{ activeLine.settledAmount }} {{ current.currency || 'CNY' }}</span
                      >
                    </p>
                    <p v-if="activeLine.financeRequired">
                      应收 {{ activeLine.expectedRefund || activeLine.amount }} · 累计已收
                      {{ activeLine.settledAmount || '0.00' }} {{ current.currency || 'CNY' }}
                    </p>
                    <article v-for="payment in activeLine.payments || []" :key="payment.id" class="event">
                      <strong>{{ payment.reference }} · {{ payment.amount }} {{ current.currency || 'CNY' }}</strong>
                      <p>{{ payment.at }} · {{ payment.reason }}</p>
                    </article>
                  </section>
                  <section class="detail-section">
                    <h2>协办任务</h2>
                    <p v-if="!activeLine.collaborations.length" class="muted">
                      尚无协办。可以由主承办创建，必需协办完成前不能推进。
                    </p>
                    <article v-for="task in activeLine.collaborations" :key="task.id" class="collaboration">
                      <h3>
                        {{ task.title }}
                        <span class="badge">{{
                          { TODO: '待接收', ACTIVE: '办理中', REVIEW: '待独立复核', DONE: '已完成' }[task.status]
                        }}</span>
                      </h3>
                      <p>{{ roleName(task.owner) }} · {{ task.required ? '必需，阻断推进' : '非必需' }}</p>
                      <p class="prose">{{ task.result || '尚未提交结果' }}</p>
                      <div class="toolbar">
                        <button
                          v-if="task.owner === actor && task.status === 'TODO'"
                          @click="openAction('collab_accept', { taskId: task.id })"
                        >
                          接收协办</button
                        ><button
                          v-if="task.owner === actor && task.status === 'ACTIVE'"
                          @click="openAction('collab_submit', { taskId: task.id })"
                        >
                          提交协办结果</button
                        ><button
                          v-if="
                            task.owner !== actor &&
                            task.status === 'REVIEW' &&
                            (actor === activeLine.owner || actor === 'coordinator')
                          "
                          @click="openAction('collab_review', { taskId: task.id })"
                        >
                          独立复核协办
                        </button>
                      </div>
                    </article>
                  </section>
                  <section class="detail-section">
                    <h2>申诉轨迹</h2>
                    <article v-for="appeal in activeLine.appeals" :key="appeal.id" class="event">
                      <strong>{{ appeal.target }} · 第{{ appeal.round }}次 · {{ appeal.status }}</strong>
                      <p>{{ appeal.result }}</p>
                    </article>
                    <p v-if="!activeLine.appeals.length" class="muted">
                      未登记申诉。平台和供应商/航司分别记录，可多轮补充，不能把处理中视为终结。
                    </p>
                  </section>
                  <section class="detail-section">
                    <h2>责任提案与交接</h2>
                    <p>
                      归因：{{ activeLine.attribution }} · {{ activeLine.responsibilityStatus }} ·
                      {{ activeLine.responsiblePerson ? roleName(activeLine.responsiblePerson) : '未指定个人' }}
                    </p>
                    <p>被认定为责任人不自动获得整单访问权限，不自动扣分或处罚。</p>
                    <div v-if="activeLine.transfer" class="callout">
                      待转给 {{ roleName(activeLine.transfer.to) }}；{{
                        activeLine.transfer.reason
                      }}。确认前原承办仍负责，截止时间不重置。
                    </div>
                    <p v-if="activeLine.waitingFor">
                      等待 {{ activeLine.waitingFor }}；下次跟进 {{ activeLine.followUpAt }}
                    </p>
                    <div class="toolbar">
                      <button
                        v-if="actor === 'reviewer' && activeLine.responsibilityStatus === '待独立复核'"
                        @click="openAction('responsibility_review')"
                      >
                        复核责任提案
                      </button>
                    </div>
                  </section>
                </template>
              </template>
              <div
                v-if="
                  actor === 'coordinator' &&
                  !current.historyOnly &&
                  current.status !== 'CLOSED' &&
                  current.status !== 'VOID'
                "
                class="controlbar"
              >
                <button @click="openAction(current.paused ? 'resume' : 'pause')">
                  {{ current.paused ? '恢复主单' : '挂起主单' }}</button
                ><button class="danger-text" @click="openAction('void')">作废（保留档案）</button>
              </div>
            </template>
            <template v-else-if="page === 'report'"
              ><h1>分析与日报演练</h1>
              <p>只统计这次演练产生的动作和当前任务，不用模拟数值证明真实人员绩效。没有样本不评优劣。</p>
              <div class="metrics">
                <article>
                  <strong>{{
                    tasks(state).filter((item) => actor === 'coordinator' || item.owner === actor).length
                  }}</strong
                  ><span>当前获权任务</span>
                </article>
                <article>
                  <strong>{{ scopedEvents.length }}</strong
                  ><span>本次演练操作数</span>
                </article>
                <article>
                  <strong>{{
                    scopedEvents.filter((event) => event.action === 'review' && event.after !== '调查取证').length
                  }}</strong
                  ><span>审核批准动作（非去重首审率）</span>
                </article>
              </div>
              <div class="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>人员</th>
                      <th>当前任务</th>
                      <th>逾期</th>
                      <th>缺期限</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="person in reportPeople" :key="person.id">
                      <td>{{ person.name }}</td>
                      <td>{{ tasks(state).filter((task) => task.owner === person.id).length }}</td>
                      <td>{{ tasks(state).filter((task) => task.owner === person.id && task.overdue).length }}</td>
                      <td>{{ tasks(state).filter((task) => task.owner === person.id && !task.dueAt).length }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="callout">
                排名口径、公开范围、最小样本和工作日历尚待业务确认，原型不生成综合绩效榜。实际日报须冻结来源版本、人工核对发布；申诉成功不等于追回到账。
              </div>
              <button @click="captureSnapshot">捕获演练快照（不发布）</button>
              <pre v-if="snapshot">{{ snapshot }}</pre>
            </template>
            <template v-else-if="page === 'settings'"
              ><h1>规则与边界</h1>
              <p>下列是本DEMO采用的可见假设，不是正式批准配置。请通过右侧意见修改，而不是默默启用生产。</p>
              <dl class="analysis">
                <div>
                  <dt>分派建议</dt>
                  <dd>平台A → 陈承办；平台B → 周承办；无法匹配或有冲突 → 林协调。正式人员来自中台授权目录。</dd>
                </div>
                <div>
                  <dt>流程建议</dt>
                  <dd>接收 → 核实/分配 → 接单 → 调查 → 申诉或差异 → 独立审核 → 必要财务 → 整单结案 → 整改。</dd>
                </div>
                <div>
                  <dt>通知建议</dt>
                  <dd>任务产生后站内提醒、超期单列；站外渠道、频率、升级时限必须另行批准。</dd>
                </div>
                <div>
                  <dt>迁移建议</dt>
                  <dd>
                    中台唯一办理入口；旧Java/Python事实、附件与日志保留来源。未迁移材料不声称已齐备；旧入口仅在正式验收和切换后关闭。
                  </dd>
                </div>
                <div>
                  <dt>双窗口</dt>
                  <dd>
                    仅同一浏览器的原型窗口联动，不是多人在线协作。意见保存在本机，可导出JSON给产品经理；正式共享评审需单独存储与账号。
                  </dd>
                </div>
              </dl>
              <button @click="advanceClock">演练时钟前进3天，观察逾期</button></template
            >
            <template v-else-if="page === 'acceptance'"
              ><h1>流程覆盖与验收记录</h1>
              <p>系统自检不代替你的批准。可以分批验收；发生版本/规则变化后需重验受影响项。</p>
              <div class="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>需求</th>
                      <th>功能</th>
                      <th>页面评审</th>
                      <th>意见</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="node in nodes" :key="node.id">
                      <td>{{ reqId(node.id) }}</td>
                      <td>{{ node.title }}</td>
                      <td>{{ reviews[node.id]?.status || '待验收' }}</td>
                      <td>{{ reviews[node.id]?.notes.length || 0 }}</td>
                      <td><button @click="focusDoc(node.id)">查看说明 / 验收</button></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <h2>版本批准关口</h2>
              <p>只有你明确批准的范围才能交开发。以下记录是你的本机审核声明，不是真实账号签名，也不会自动启动开发。</p>
              <label>审核人姓名<a-input v-model:value="approvalName" placeholder="请填写你的姓名" /></label
              ><label
                >批准范围（仅可选择已通过项）<a-select
                  v-model:value="approvalIds"
                  mode="multiple"
                  :options="
                    nodes
                      .filter((node) => reviews[node.id]?.status === '已通过')
                      .map((node) => ({ value: node.id, label: `${reqId(node.id)} ${node.title}` }))
                  " /></label
              ><label>范围、排除项和剩余问题<a-textarea v-model:value="approvalReason" :rows="3" /></label
              ><a-checkbox v-model:checked="approvalConfirm"
                >我已实际演练并核对以上范围，仅批准此原型版本，不包含部署或生产切换</a-checkbox
              >
              <p><button class="primary" @click="approveVersion">记录我的批准范围</button></p>
              <article v-for="approval in approvals" :key="approval.id" class="event">
                <strong>{{ approval.name }} · {{ approval.version }}</strong>
                <p>{{ approval.at }} · {{ approval.ids.map(reqId).join('、') }}</p>
                <p>{{ approval.reason }}</p>
                <p>
                  适用性：{{
                    approval.ids.every((key) => reviews[key]?.status === '已通过')
                      ? '页面评审仍为通过；后续实质改版需复验'
                      : '存在改为需修改的项目，受影响批准不得直接沿用'
                  }}
                </p>
              </article></template
            >
          </main>
        </div>
        <footer v-if="activeScenario && showGuide" class="guide">
          <div>
            <strong
              >演练导航 · {{ activeScenario.title }} · {{ guideIndex + 1 }}/{{ activeScenario.steps.length }}</strong
            >
            <p>{{ activeScenario.steps[guideIndex]?.instruction }}</p>
          </div>
          <div class="toolbar">
            <button :disabled="guideIndex === 0" @click="guideIndex--">上一步</button
            ><button class="primary" @click="goGuide">切换人员并打开此步</button
            ><button :disabled="guideIndex === activeScenario.steps.length - 1" @click="guideIndex++">下一步</button>
          </div>
          <small>导航仅带你去页面，不替你完成任务；步骤未办完，状态校验仍会阻止跳过。</small>
        </footer>
      </section>
      <PanelDivider v-if="showDocs && !docOnly && !simOnly" v-model="split" />
      <PrdPanel
        v-if="(showDocs && !simOnly) || docOnly"
        v-model="docTab"
        :title="`${reqId(doc.id)} · ${doc.title}`"
        :subtitle="`${VERSION} · 原型建议，待业务审核`"
        :tabs="docTabs"
      >
        <label
          >功能模块<a-select
            :value="docId"
            :options="nodes.map((node) => ({ value: node.id, label: node.title }))"
            @change="docId = String($event)"
        /></label>
        <ProductGuide
          v-if="docTab === 'fields' || docTab === 'flows'"
          :node="doc.id"
          :mode="docTab === 'fields' ? 'fields' : 'flows'"
        />
        <p class="prototype-coverage">
          <strong>本DEMO实际范围：</strong
          >{{ actualCoverage[doc.id] || '页面、模拟操作与规则说明；正式服务端实现待你批准后另行开发。' }}
        </p>
        <template v-if="docTab === 'operation'"
          ><h2>要解决什么</h2>
          <p>{{ doc.goal }}</p>
          <h3>谁来操作</h3>
          <p>{{ doc.actor }}</p>
          <h3>填写与操作点</h3>
          <ol>
            <li v-for="input in doc.inputs" :key="input">{{ input }}</li>
          </ol>
          <h3>完成后的结果</h3>
          <ul>
            <li v-for="outcome in doc.outcomes" :key="outcome">{{ outcome }}</li>
          </ul>
          <ProductGuide :node="doc.id" mode="flows" /><ProductGuide :node="doc.id" mode="fields" /></template
        ><template v-else-if="docTab === 'rules'"
          ><h2>权限、前置与异常</h2>
          <ul>
            <li v-for="rule in doc.rules" :key="rule">{{ rule }}</li>
          </ul>
          <h3>待你确认</h3>
          <ul>
            <li v-for="pending in doc.pending" :key="pending">{{ pending }}</li>
            <li v-if="!doc.pending.length">本页无单列问题；仍需核对完整场景。</li>
          </ul>
          <div class="callout">
            文字描述不表示后台已经实现。正式权限、存储、外部接口及迁移仍需开发后验收。
          </div></template
        ><template v-else-if="docTab === 'checks'"
          ><h2>你可以这样验收</h2>
          <label v-for="(check, index) in doc.checks" :key="index" class="accept-check"
            ><input
              type="checkbox"
              :checked="!!reviews[doc.id]?.checks[index]"
              @change="toggleCheck(doc.id, index)"
            /><span>{{ check }}</span></label
          >
          <h3>记录页面评审结果</h3>
          <label>评审人<a-input v-model:value="reviewerName" placeholder="填写你的姓名，不自动认定身份" /></label
          ><label>评审结论 / 暂缓原因<a-textarea v-model:value="reviewReason" :rows="3" /></label>
          <div class="toolbar">
            <button class="primary" @click="reviewNode('已通过')">这页通过</button
            ><button @click="reviewNode('需修改')">需要修改</button
            ><button @click="reviewNode('暂不做')">暂不做</button>
          </div>
          <p>当前：{{ reviews[doc.id]?.status || '待验收' }} · {{ reviews[doc.id]?.by || '尚未评审' }}</p>
          <p class="muted">勾选只记录你的检查，不自动证明功能通过。整版批准请到左侧“覆盖与验收”。</p></template
        ><template v-else-if="docTab === 'comments'"
          ><h2>把意见留在当前步骤</h2>
          <label>你的姓名<a-input v-model:value="reviewerName" /></label
          ><label
            >哪里不对？你希望怎样？<a-textarea
              v-model:value="comment"
              :rows="5"
              placeholder="例如：金额超出范围才需要主管复核；普通单直接给平台负责人。" /></label
          ><button class="primary" @click="addComment">保存意见并标为需修改</button>
          <article v-for="note in reviews[doc.id]?.notes || []" :key="note.id" class="event">
            <strong>{{ note.by }} · {{ note.at }}</strong>
            <p class="prose">{{ note.text }}</p>
            <span class="badge">待产品经理处理</span>
          </article>
          <p class="muted">
            保存只在本机。体验结束点击顶部“导出体验与验收记录”，把JSON文件发给我，我按这些意见修改，你再复验。
          </p></template
        >
        <template #footer>
          <button @click="docTab = 'comments'">对此步骤提意见</button
          ><button @click="navigate('acceptance')">查看全部覆盖项</button>
        </template>
      </PrdPanel>
    </div>
    <FormDialog
      v-model:open="modal"
      :title="actionNames[action] || '接收ADM（合成演练）'"
      :dirty="dirty"
      :error="formError"
      :ok-text="action === 'intake' ? (intakePreview ? '确认接收并生成任务' : '先预览核对') : '确认模拟操作'"
      @submit="submitAction"
    >
      <div class="callout">
        所有操作仅影响此DEMO；不使用真实客户或供应资料。{{
          action === 'intake' ? '先预览，再确认；复制不继承处理结果。' : '完成后会更新模拟状态、任务与留痕。'
        }}
      </div>
      <div v-if="actionSpecs[action]" class="action-contract">
        <strong>{{ actionSpecs[action]?.name }}</strong>
        <p>{{ actionSpecs[action]?.when }}</p>
        <p>完成后：{{ actionSpecs[action]?.result }}</p>
      </div>
      <template v-if="action === 'intake'">
        <IntakeFields v-model="draft" :types="typeOptions" :state="state" />
        <div v-if="intakePreview" class="callout success">
          预览通过：{{ draft.admNo }}，共 {{ draft.amount }} {{ draft.currency }}。修改后重新预览，确认后才生成任务。
        </div>
      </template>
      <template v-else-if="['edit', 'preliminary'].includes(action)">
        <FormGrid
          ><label>ADM号 *<a-input v-model:value="draft.admNo" /></label
          ><label>供应商 *<a-input v-model:value="draft.supplier" /></label
          ><label
            >来源主体<a-select
              v-model:value="draft.sourceType"
              :options="['航司', '供应商', '平台'].map((value) => ({ value }))" /></label
          ><label>航司代码 *<a-input v-model:value="draft.airline" /></label
          ><label>下发日期 *<DateField v-model="draft.issuedOn" /></label
          ><label>供应回复截止 *<DateField v-model="draft.replyDue" /></label
          ><label>主单金额 *<a-input v-model:value="draft.amount" /></label
          ><label
            >币种（本单固定）<strong>{{ current?.currency || 'CNY' }}</strong></label
          ><label class="form-span">ADM内容 *<a-textarea v-model:value="draft.description" :rows="3" /></label
          ><label class="form-span">备注<a-textarea v-model:value="draft.remark" :rows="2" /></label
        ></FormGrid>
        <div v-for="(line, index) in draft.lines" :key="line.id" class="intake-row">
          <h3>订单子项 {{ Number(index) + 1 }}</h3>
          <FormGrid
            ><label>订单号 *<a-input v-model:value="line.orderNo" /></label
            ><label>票号<a-input v-model:value="line.ticketNo" /></label
            ><label
              >平台<a-select
                v-model:value="line.platform"
                :options="['平台A', '平台B'].map((value) => ({ value }))" /></label
            ><label
              >业务<a-select
                v-model:value="line.business"
                :options="['出票', '退票', '改签'].map((value) => ({ value }))" /></label
            ><label>金额 *<a-input v-model:value="line.amount" /></label
            ><label>PNR<a-input v-model:value="line.pnr" /></label
            ><label>店铺 / 细分站点<a-input v-model:value="line.site" /></label
          ></FormGrid>
        </div>
      </template>
      <template v-else-if="action === 'recovery'"
        ><FormGrid
          ><label>恢复编码 *<a-input v-model:value="draft.recoveryCode" /></label
          ><label>恢复截止<DateField v-model="draft.recoveryDue" with-time /></label
          ><label class="form-span"
            >恢复结果（完成时必填）<a-textarea v-model:value="draft.recoveryResult" :rows="3" /></label
        ></FormGrid>
        <p>结果留空则仍待恢复；填写结果并引用证据后完成恢复，继续本单调查。</p></template
      >
      <template v-else-if="['record', 'submit'].includes(action)">
        <button @click="fillExample">填入合成处理示例（可修改）</button>
        <FormGrid>
          <label class="form-span"
            >本次处理意见 / 结果 *<a-textarea v-model:value="draft.conclusion" :rows="3"
          /></label>
          <label
            >具体错误类型 *<a-select v-model:value="draft.diffType" :options="typeOptions.map((value) => ({ value }))"
          /></label>
          <label
            >原因归属 *<a-select
              v-model:value="draft.attribution"
              :options="['人为', '系统问题', '非人为/政策原因', '待认定'].map((value) => ({ value }))"
          /></label>
          <label
            >处理方式<a-select
              v-model:value="draft.appealDecision"
              :options="['申诉', '不申诉'].map((value) => ({ value }))"
          /></label>
          <label v-if="draft.appealDecision === '不申诉'"
            >不申诉原因 *<a-textarea v-model:value="draft.appealReason" :rows="2"
          /></label>
          <label><a-checkbox v-model:checked="draft.financeRequired">需要后续回款</a-checkbox></label>
          <label v-if="draft.financeRequired">应收原币金额 *<a-input v-model:value="draft.expectedRefund" /></label>
          <label v-if="!draft.financeRequired">无需回款依据 *<a-input v-model:value="draft.financeReason" /></label>
          <label v-if="draft.appealDecision === '不申诉'"
            ><a-checkbox v-model:checked="draft.differenceRecorded">已在外部登记差异（演练）</a-checkbox></label
          >
          <label v-if="draft.appealDecision === '不申诉'"
            >差异登记编号 / 无需登记依据 *<a-input v-model:value="draft.differenceReason"
          /></label>
        </FormGrid>
        <details>
          <summary>等待、恢复编码和补充分析（按需填写）</summary>
          <FormGrid>
            <label>等待事项<a-input v-model:value="draft.waitingFor" /></label>
            <label>下次跟进<DateField v-model="draft.followUpAt" with-time /></label>
            <label><a-checkbox v-model:checked="draft.recoveryRequired">需要恢复编码</a-checkbox></label>
            <label v-if="draft.recoveryRequired">恢复编码 *<a-input v-model:value="draft.recoveryCode" /></label>
            <label v-if="draft.recoveryRequired">恢复结果 *<a-input v-model:value="draft.recoveryResult" /></label>
            <label v-if="draft.recoveryRequired">恢复截止<DateField v-model="draft.recoveryDue" with-time /></label
            ><label>PNR<a-input v-model:value="draft.pnr" /></label
            ><label>店铺 / 细分站点<a-input v-model:value="draft.site" /></label>
            <label v-for="field in analysisFields.filter((item) => item.key !== 'conclusion')" :key="field.key"
              >{{ field.label }}<a-textarea v-model:value="draft[field.key]" :rows="2"
            /></label>
          </FormGrid>
          <p>等待须明确跟进时间并保存，不自动免除超期；时限与恢复计时规则待确认，不自动拒单。</p>
        </details>
      </template>
      <template v-else-if="action === 'match'"
        ><FormGrid
          ><label>核实后的订单号 *<a-input v-model:value="draft.orderNo" /></label
          ><label
            >平台<a-select
              v-model:value="draft.platform"
              :options="['平台A', '平台B'].map((value) => ({ value }))" /></label
          ><label class="form-span"
            ><a-checkbox v-model:checked="draft.autoAssign"
              >匹配成功后按演练规则生成到人任务；不勾选则进入待分派</a-checkbox
            ></label
          ></FormGrid
        ></template
      >
      <template v-else-if="['assign', 'transfer_request', 'collab_create'].includes(action)"
        ><FormGrid
          ><label>接收人 *<AccountSelect v-model="draft.owner" :options="handlePeople" /></label
          ><label v-if="action === 'collab_create'">协办目标 *<a-input v-model:value="draft.title" /></label
          ><label v-if="action === 'collab_create'"
            ><a-checkbox v-model:checked="draft.required">必需协办（完成前阻断推进）</a-checkbox></label
          ></FormGrid
        ></template
      >
      <template v-else-if="action === 'appeal'"
        ><FormGrid
          ><label
            >申诉对象 *<a-select
              v-model:value="draft.target"
              :options="['平台', '供应商', '航司'].map((value) => ({ value }))" /></label
          ><label
            >本次结果 *<a-select
              v-model:value="draft.status"
              :options="['处理中', '成功', '部分成功', '失败', '撤回'].map((value) => ({ value }))" /></label
          ><label class="form-span">申诉材料 / 回复说明 *<a-textarea v-model:value="draft.result" :rows="4" /></label>
          <label v-if="['部分成功', '失败'].includes(draft.status)"
            >本项承担金额 *<a-input v-model:value="draft.borneAmount"
          /></label>
          <label><a-checkbox v-model:checked="draft.financeRequired">审核后继续跟进回款</a-checkbox></label
          ><label v-if="draft.financeRequired"
            >应收原币金额 *<a-input v-model:value="draft.expectedRefund" /></label></FormGrid
      ></template>
      <template v-else-if="action === 'difference'"
        ><a-checkbox v-model:checked="draft.recorded">已录差异（不勾选必须说明无需登记的依据）</a-checkbox></template
      >
      <template v-else-if="['review', 'collab_review', 'responsibility_review', 'remediation_review'].includes(action)"
        ><a-checkbox v-model:checked="draft.approved">批准（取消勾选表示退回补充）</a-checkbox>
        <p>只审核当前节点，不代表主单自动结案或财务到账。</p></template
      >
      <template v-else-if="action === 'finance'"
        ><FormGrid
          ><label>核对凭证号 *<a-input v-model:value="draft.reference" /></label
          ><label>本次到账金额（当前原币）*<a-input v-model:value="draft.amount" /></label
          ><label class="form-span"
            ><a-checkbox v-model:checked="draft.confirmComplete"
              >确认累计已全部到账（部分到账可不勾选，保留财务待办）</a-checkbox
            ></label
          ></FormGrid
        ></template
      >
      <template v-else-if="['collab_submit', 'remediate'].includes(action)"
        ><label>处理结果与验证 *<a-textarea v-model:value="draft.result" :rows="4" /></label
      ></template>
      <template v-else-if="action === 'responsibility'"
        ><FormGrid
          ><label
            >归因类别 *<a-select
              v-model:value="draft.attribution"
              :options="
                ['人为差错', '系统原因', '供应商原因', '航司原因', '平台原因', '待认定'].map((value) => ({ value }))
              " /></label
          ><label
            >涉及人员（不是办理人分配）<AccountSelect
              v-model="draft.person"
              :options="handlePeople" /></label></FormGrid
      ></template>
      <template v-else-if="action === 'amount'"
        ><label>调整后明细原币金额 *<a-input v-model:value="draft.amount" /></label>
        <p>不自动平摊或覆盖原件金额；必须保留调整依据。</p></template
      >
      <template v-else-if="action === 'attach'"
        ><label class="file-button">选择本机文件（单文件2MB）<input type="file" @change="chooseAttachment" /></label>
        <p v-if="draft.dataUrl">已选择 {{ draft.name }}，仅在本机保存。</p>
        <FormGrid
          ><label>演练文本名称 *<a-input v-model:value="draft.name" /></label
          ><label
            >分类<a-select
              v-model:value="draft.category"
              :options="
                ['下发原件', '调查证据', '申诉材料', '恢复佐证', '财务凭证', '脱敏副本'].map((value) => ({ value }))
              " /></label
          ><label class="form-span"
            >演练文件全文 *<a-textarea v-model:value="draft.content" :rows="5" /></label></FormGrid
      ></template>
      <template v-else-if="action === 'share'"
        ><label
          >授权明细（清空为撤销）<a-select
            v-model:value="draft.lineIds"
            mode="multiple"
            :options="current?.lines.map((line) => ({ value: line.id, label: line.orderNo || line.id }))" /></label
        ><a-checkbox v-model:checked="draft.confirm"
          >我已核对整份演练文件，内容适合所选明细人员；不是只共享文件中的一小段</a-checkbox
        ></template
      >
      <template v-else-if="action === 'close'"
        ><ul>
          <li v-for="blocker in current ? blockers(current) : []" :key="blocker">{{ blocker }}</li>
        </ul>
        <p>结案后生成独立整改事项，不自动重开或改变已完成事实。</p></template
      >
      <label v-if="evidenceActions.includes(action)"
        >引用当前明细可读证据 *<a-select
          v-model:value="draft.evidence"
          mode="multiple"
          :options="lineFiles.map((file) => ({ value: file.id, label: file.name }))"
      /></label>
      <label v-if="reasonActions.includes(action)"
        >操作依据 / 已做事项与待办摘要 *<a-textarea
          v-model:value="draft.reason"
          :rows="3"
          placeholder="请说明为什么执行、已核对什么、下一步是什么"
      /></label>
      <p v-if="action === 'claim' || action === 'collab_accept'">
        确认接收后，任务将进入本人办理中。重复点击不会生成第二份工作。
      </p>
    </FormDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import ReviewToolbar from '../shared/ReviewToolbar.vue'
import PrdPanel from '../shared/PrdPanel.vue'
import PanelDivider from '../shared/PanelDivider.vue'
import '../shared/review.css'
import FormDialog from '../../src/components/FormDialog.vue'
import FormGrid from '../../src/components/FormGrid.vue'
import AccountSelect from '../../src/components/AccountSelect.vue'
import DateField from '../../src/components/DateField.vue'
import { VERSION, nodes, scenarios } from './definition'
import IntakeFields from './IntakeFields.vue'
import OperationsDesk from './OperationsDesk.vue'
import ProductGuide from './ProductGuide.vue'
import { actionSpecs } from './product-spec'
import { workspaceSeed, canEditCase } from './workspace'
import { prepareIntake, specificTypes } from './intake'
import {
  roles,
  roleName,
  seed,
  tasks,
  visibleLines,
  visibleFile,
  stageNames,
  stageNode,
  transition,
  submitProcessing,
  blockers,
  cents,
  cash,
  id,
  type SimState,
  type Case,
  type Task,
  type Evidence,
} from './model'
type Fields = Record<string, any>
type Review = {
  status: string
  by: string
  reason: string
  at: string
  checks: Record<number, boolean>
  notes: { id: string; by: string; at: string; text: string }[]
}
type Approval = { id: string; name: string; version: string; ids: string[]; reason: string; at: string }
const STORAGE = 'adm-review-demo-v03'
const showAdvanced = ref(false),
  showGuide = ref(false)
const state = ref<SimState>(workspaceSeed()),
  actor = ref('coordinator'),
  page = ref('ledger'),
  selectedCase = ref('case-demo-001'),
  selectedLine = ref('line-1'),
  caseTab = ref('detail'),
  docId = ref('overview'),
  docTab = ref('operation'),
  notice = ref(''),
  showDocs = ref(true),
  split = ref(65),
  guideIndex = ref(0),
  search = ref(''),
  appliedSearch = ref(''),
  snapshot = ref('')
const docOnly = location.hash === '#prd',
  simOnly = location.hash === '#sim'
const reviews = ref<Record<string, Review>>({}),
  approvals = ref<Approval[]>([]),
  reviewerName = ref(''),
  reviewReason = ref(''),
  comment = ref(''),
  approvalName = ref(''),
  approvalReason = ref(''),
  approvalIds = ref<string[]>([]),
  approvalConfirm = ref(false)
const modal = ref(false),
  action = ref(''),
  draft = ref<Fields>({}),
  baseline = ref(''),
  formError = ref(''),
  intakePreview = ref('')
let expected = 0,
  contextCase = '',
  contextLine = '',
  child: Window | null = null,
  receiving = false
const allMenus = [
  { id: 'work', title: '我的工作', sub: '到人任务与提醒' },
  { id: 'ledger', title: 'ADM台账', sub: '主单 / 订单 / 连续办理' },
  { id: 'intake', title: '录入与核实', sub: '预罚 / 正式 / 多票号' },
  { id: 'dispatch', title: '团队督办', sub: '分派 / 转交 / 协办' },
  { id: 'recovery', title: '恢复编码', sub: '节点期限与结果' },
  { id: 'appeals', title: '申诉跟进', sub: '多对象 / 多轮次' },
  { id: 'reviewQueue', title: '审核工作台', sub: '通过 / 退回' },
  { id: 'financeQueue', title: '回款工作台', sub: '部分 / 多次 / 结清' },
  { id: 'notifications', title: '通知与回执', sub: '提醒 / 接收确认' },
  { id: 'report', title: '统计与日报', sub: '进度 / 积压 / 原币' },
  { id: 'exchange', title: '导入导出', sub: '统一模板 / 预览' },
  { id: 'history', title: '历史档案', sub: '只读 / 复制引用' },
  { id: 'settings', title: '规则设置', sub: '分派 / 字典 / 汇率' },
  { id: 'overview', title: '旧演练工具', sub: '可选场景重置' },
  { id: 'acceptance', title: '覆盖与验收', sub: '意见与版本关口' },
]
const menus = computed(() =>
  allMenus.filter((menu) => showAdvanced.value || !['overview', 'acceptance'].includes(menu.id)),
)
const deskPages = [
  'ledger',
  'recovery',
  'appeals',
  'reviewQueue',
  'financeQueue',
  'notifications',
  'exchange',
  'settings',
  'report',
  'history',
]
const typeOptions = computed(() => state.value.rules?.types.map((item) => item.name) || specificTypes)
const landscape = [
  ['接收与历史', '单条表单、多票号子项、预览去重', '复杂批量后置；不继承旧完成状态'],
  ['订单处理', '出退改、多平台、PNR、站点、分摊', '主子单保留；任务入口重设计'],
  ['责任与协作', '接单、交接、协办、复核、整改', '办理责任与差错归因分开'],
  ['申诉与差异', '多对象、多轮记录、差异登记', '合并流程，原始依据保留'],
  ['财务与结案', '凭证核对、前置检查、授权重开', '申诉成功不代替真实结算'],
  ['附件与追溯', '授权明细、全文、共享撤销、历史', '旧文件未迁移不宣称齐备'],
  ['人员分析', '本人/团队任务、逾期、演练快照', '不复用旧看板金额作绩效'],
  ['旧系统切换', 'Java/Python能力归并，中台唯一入口', '生产迁移、旧入口关闭均未执行'],
]
const caseTabs = [
  { id: 'detail', title: '订单处理' },
  { id: 'attachments', title: '原件与附件' },
  { id: 'close', title: '结案与整改' },
  { id: 'history', title: '操作历史' },
]
const docTabs = [
  { id: 'operation', title: '功能操作' },
  { id: 'fields', title: '字段说明' },
  { id: 'flows', title: '按钮与流转' },
  { id: 'rules', title: '规则与待定' },
  { id: 'checks', title: '验收' },
  { id: 'comments', title: '提意见' },
]
const actualCoverage: Record<string, string> = {
  intake: '结构化单条与CSV预览导入、多票号、预罚核实、转正式、编辑、复制及参考换算；订单候选和汇率采用本地演示值。',
  attachments: '可选择本机文件，预览图片/PDF/文本、下载及共享；不上传服务器，不执行旧附件迁移。',
  report: '当前范围进度、人员积压排序、分币种金额和可读日报导出；不真实群发或计算正式绩效。',
  settings: '本机可保存分派、错误类型/外部代码、供应默认币种、参考汇率及预警规则；后续新单生效，不回溯重派。',
  acceptance: '可记录意见、逐页验收、分批批准声明和JSON导出/恢复；仅本机保存，不是多人在线审批或身份签名。',
}
const analysisFields: { key: 'facts' | 'cause' | 'proposal' | 'conclusion' | 'remark'; label: string }[] = [
  { key: 'facts', label: '事实与核实依据' },
  { key: 'cause', label: '原因分析' },
  { key: 'proposal', label: '处理建议' },
  { key: 'conclusion', label: '处理结论' },
  { key: 'remark', label: '业务备注' },
]
const actionNames: Record<string, string> = {
  publish: '发布并生成任务',
  match: '核实订单并分派',
  assign: '指定承办人',
  claim: '接收我的任务',
  record: '保存处理草稿',
  submit: '提交处理 / 审核',
  appeal: '登记一轮申诉',
  appeal_next: '提交申诉结果',
  difference: '登记差异并提交审核',
  review: '独立审核 / 退回',
  finance: '确认回款',
  transfer_request: '发起确认式转交',
  transfer_accept: '接受交接',
  transfer_reject: '驳回交接',
  transfer_cancel: '取消待确认交接',
  collab_create: '创建协办任务',
  collab_accept: '接收协办',
  collab_submit: '提交协办结果',
  collab_review: '独立复核协办',
  responsibility: '提出责任认定',
  responsibility_review: '独立复核责任',
  amount: '调整明细分摊',
  attach: '新增演练证据',
  share: '明确整份附件共享',
  close: '核对并结案',
  reopen: '授权重开',
  remediate: '完成结案后整改',
  pause: '挂起主单',
  resume: '恢复主单',
  void: '作废并保留档案',
  edit: '编辑基础信息',
  preliminary: '预罚转正式',
  recovery: '保存恢复编码',
  lock: '锁定本人编辑',
  unlock: '解除办理锁',
}
const primaryActions = [
  'claim',
  'match',
  'assign',
  'submit',
  'appeal',
  'difference',
  'review',
  'finance',
  'transfer_accept',
]
const evidenceActions = [
  'recovery',
  'record',
  'submit',
  'appeal',
  'difference',
  'finance',
  'collab_submit',
  'responsibility',
  'remediate',
]
Object.assign(actionNames, { remediation_accept: '接收整改任务', remediation_review: '独立复核整改' })
const reasonActions = [
  'edit',
  'preliminary',
  'unlock',
  'match',
  'assign',
  'transfer_request',
  'transfer_accept',
  'transfer_reject',
  'transfer_cancel',
  'review',
  'collab_review',
  'responsibility',
  'responsibility_review',
  'remediation_review',
  'finance',
  'difference',
  'amount',
  'share',
  'close',
  'reopen',
  'pause',
  'resume',
  'void',
]
const handlePeople = roles
  .filter((role) => ['handlerA', 'handlerB', 'lead'].includes(role.id))
  .map((role) => ({ id: role.id, name: role.name }))
const current = computed(() =>
  state.value.cases.find(
    (item) =>
      item.id === selectedCase.value &&
      (visibleLines(item, actor.value).length ||
        actor.value === 'coordinator' ||
        (item.status === 'CLOSED' && item.remediation.owner === actor.value)),
  ),
)
const activeLine = computed(() =>
  current.value ? visibleLines(current.value, actor.value).find((line) => line.id === selectedLine.value) : undefined,
)
const readableFiles = computed(() =>
  current.value
    ? current.value.files.filter((file) => visibleFile(file, actor.value, visibleLines(current.value!, actor.value)))
    : [],
)
const lineFiles = computed(() =>
  readableFiles.value.filter(
    (file) => file.lineId === activeLine.value?.id || file.shared.includes(activeLine.value?.id || ''),
  ),
)
const activeScenario = computed(() => scenarios.find((item) => item.id === state.value.scenario))
const doc = computed(() => nodes.find((node) => node.id === docId.value) || nodes[0]!)
const displayTasks = computed(() =>
  tasks(state.value).filter(
    (task) =>
      (page.value === 'dispatch' &&
        (actor.value === 'coordinator' ||
          (actor.value === 'lead' &&
            state.value.cases
              .find((item) => item.id === task.caseId)
              ?.lines.some((line) => line.id === task.lineId && line.supervisor === 'lead')))) ||
      task.owner === actor.value,
  ),
)
const visibleCases = computed(() =>
  state.value.cases.filter(
    (item) =>
      visibleLines(item, actor.value).length &&
      (actor.value === 'coordinator'
        ? JSON.stringify(item)
        : JSON.stringify([item.admNo, ...visibleLines(item, actor.value)])
      )
        .toLowerCase()
        .includes(appliedSearch.value.toLowerCase()),
  ),
)
const visibleEvents = computed(() =>
  state.value.events.filter(
    (event) =>
      event.caseId === current.value?.id &&
      (actor.value === 'coordinator' ||
        visibleLines(current.value!, actor.value).some((line) => line.id === event.lineId)),
  ),
)
const scopedEvents = computed(() =>
  state.value.events.filter((event) => actor.value === 'coordinator' || event.actor === actor.value),
)
const reportPeople = computed(() => roles.filter((role) => actor.value === 'coordinator' || role.id === actor.value))
const dirty = computed(() => JSON.stringify(draft.value) !== baseline.value)
const permitted = computed(() => {
  const item = current.value,
    line = activeLine.value
  if (
    !item ||
    !line ||
    item.historyOnly ||
    item.paused ||
    item.status === 'VOID' ||
    (line.lockedBy && line.lockedBy !== actor.value && !['reviewer', 'finance'].includes(actor.value))
  )
    return []
  if (item.status === 'CLOSED')
    return actor.value === 'finance' && line.stage === 'DONE' && line.financeRequired && !line.financeReference
      ? ['finance']
      : []
  const result: string[] = []
  if (actor.value === 'coordinator') {
    if (line.stage === 'MATCH') result.push('match')
    if (['ASSIGN', 'ACCEPT', 'INVESTIGATE'].includes(line.stage)) result.push('assign', 'amount')
  }
  if (line.owner === actor.value) {
    if (line.stage === 'ACCEPT') result.push('claim')
    if (line.stage === 'INVESTIGATE') result.push('record', 'submit', 'collab_create', 'responsibility')
    if (line.stage === 'APPEAL') result.push('appeal', 'appeal_next')
    if (line.stage === 'DIFFERENCE') result.push('difference')
    if (['ACCEPT', 'INVESTIGATE', 'APPEAL', 'DIFFERENCE'].includes(line.stage))
      result.push(line.transfer ? 'transfer_cancel' : 'transfer_request')
  }
  if (line.transfer?.to === actor.value) result.push('transfer_accept', 'transfer_reject')
  if (actor.value === 'reviewer' && line.stage === 'REVIEW') result.push('review')
  if (actor.value === 'finance' && line.stage === 'DONE' && line.financeRequired && !line.financeReference)
    result.push('finance')
  return item.preliminary
    ? result.filter((value) => !['submit', 'appeal', 'appeal_next', 'difference', 'review', 'finance'].includes(value))
    : result
})
const nextExperienceTask = computed(
  () =>
    tasks(state.value).find((task) => task.caseId === selectedCase.value && task.kind === '结案') ||
    tasks(state.value).find(
      (task) =>
        task.caseId === selectedCase.value &&
        task.lineId === selectedLine.value &&
        task.owner !== actor.value &&
        !['跟进', '恢复编码'].includes(task.kind),
    ),
)
function experienceNext() {
  const task = nextExperienceTask.value
  if (!task) return
  actor.value = task.owner
  openTask(task)
}
const reqId = (key: string) => `ADM-${String(nodes.findIndex((node) => node.id === key) + 1).padStart(3, '0')}`
const caseStatus = (item: Case) =>
  item.paused ? '已挂起' : { DRAFT: '草稿', ACTIVE: '办理中', CLOSED: '已结案', VOID: '已作废' }[item.status]
const allocated = (item: Case) => {
  try {
    return cash(item.lines.reduce((sum, line) => sum + cents(line.amount), 0))
  } catch {
    return '金额待核对'
  }
}
function focusDoc(key: string) {
  docId.value = nodes.some((node) => node.id === key) ? key : 'overview'
  showDocs.value = true
}
function navigate(key: string) {
  page.value = key
  focusDoc(
    (
      {
        work: 'accept',
        dispatch: 'assign',
        ledger: 'overview',
        history: 'exchange',
        appeals: 'appeal',
        reviewQueue: 'review',
        financeQueue: 'finance',
      } as Record<string, string>
    )[key] || key,
  )
}
function changeDeskRole(value: string) {
  const previous = page.value
  changeActor(value)
  navigate(previous)
}
function changeActor(value: unknown) {
  actor.value = String(value)
  if (current.value) {
    selectedLine.value = visibleLines(current.value, actor.value)[0]?.id || ''
  } else {
    page.value = 'work'
    selectedCase.value = ''
    selectedLine.value = ''
  }
  notice.value = `已切换 ${roleName(actor.value)}；仅演练身份，不是真实授权`
}
function chooseLine(value: unknown) {
  selectedLine.value = String(value)
  if (activeLine.value) focusDoc(stageNode[activeLine.value.stage])
}
function changeTab(key: string) {
  caseTab.value = key
  focusDoc(
    key === 'detail'
      ? activeLine.value
        ? stageNode[activeLine.value.stage]
        : 'overview'
      : key === 'history'
        ? 'overview'
        : key,
  )
}
function openCase(caseId: string, lineId?: string, node?: string) {
  selectedCase.value = caseId
  const item = state.value.cases.find((item) => item.id === caseId)
  selectedLine.value = lineId || (item ? visibleLines(item, actor.value)[0]?.id : '') || ''
  page.value = 'case'
  caseTab.value =
    node === 'attachments' ? 'attachments' : node === 'close' || node === 'remediation' ? 'close' : 'detail'
  focusDoc(node || (activeLine.value ? stageNode[activeLine.value.stage] : 'overview'))
}
function openTask(task: Task) {
  openCase(task.caseId, task.lineId, task.node)
}
function startScenario(key: string) {
  if (!confirm('重置当前模拟业务？你的意见和验收记录保留；未导出的业务演练进度会替换。')) return
  state.value = seed(key)
  guideIndex.value = 0
  actor.value =
    key === 'cashflow' ? 'finance' : key === 'exception' ? 'coordinator' : key === 'closed' ? 'handlerB' : 'handlerA'
  selectedCase.value = state.value.cases[0]!.id
  selectedLine.value = visibleLines(state.value.cases[0]!, actor.value)[0]?.id || ''
  navigate('work')
  notice.value = '场景已重置；意见和验收记录保留。可按底部指引逐步体验。'
}
function goGuide() {
  const step = activeScenario.value?.steps[guideIndex.value]
  if (!step) return
  actor.value = step.role
  const item = state.value.cases[0]!
  if (['overview', 'intake', 'report', 'settings', 'acceptance'].includes(step.node)) navigate(step.node)
  else {
    const task = tasks(state.value).find((task) => task.owner === actor.value && task.node === step.node)
    openCase(item.id, task?.lineId || visibleLines(item, actor.value)[0]?.id, step.node)
  }
}
function openNotice(item: SimState['notices'][number]) {
  const parent = state.value.cases.find((value) => value.id === item.caseId)
  if (!parent || (item.lineId && !visibleLines(parent, actor.value).some((line) => line.id === item.lineId))) {
    notice.value = '该任务已转交，当前人员无此明细范围。'
    return
  }
  markRead(item.id)
  openCase(
    item.caseId,
    item.lineId,
    item.lineId ? stageNode[parent.lines.find((line) => line.id === item.lineId)!.stage] : 'close',
  )
}
function markRead(key: string) {
  const note = state.value.notices.find((item) => item.id === key && item.recipient === actor.value)
  if (note) note.read = true
}
function openAction(name: string, values: Fields = {}) {
  action.value = name
  contextCase = selectedCase.value
  contextLine = selectedLine.value
  expected = state.value.version
  draft.value = {
    reason: '',
    approved: true,
    evidence: [...(activeLine.value?.evidence || [])],
    amount: activeLine.value?.amount || '',
    ...values,
  }
  if (['record', 'submit'].includes(name) && activeLine.value)
    draft.value = { ...JSON.parse(JSON.stringify(activeLine.value)), ...values }
  if (name === 'match')
    draft.value = {
      ...draft.value,
      orderNo: activeLine.value?.orderNo || '',
      platform: activeLine.value?.platform || '平台A',
      autoAssign: true,
    }
  if (name === 'appeal')
    Object.assign(draft.value, {
      target: '平台',
      status: '处理中',
      result: '',
      borneAmount: activeLine.value?.borneAmount || '',
      financeRequired: activeLine.value?.financeRequired || false,
    })
  if (name === 'appeal') draft.value.expectedRefund = activeLine.value?.expectedRefund || activeLine.value?.amount || ''
  if (name === 'finance')
    Object.assign(draft.value, {
      amount: cash(
        Math.max(
          0,
          cents(activeLine.value?.expectedRefund || activeLine.value?.amount || '0') -
            cents(activeLine.value?.settledAmount || '0'),
        ),
      ),
      confirmComplete: false,
    })
  if (['edit', 'preliminary'].includes(name) && current.value)
    draft.value = { ...JSON.parse(JSON.stringify(current.value)), reason: '' }
  if (name === 'recovery' && activeLine.value)
    draft.value = {
      ...draft.value,
      recoveryCode: activeLine.value.recoveryCode,
      recoveryResult: activeLine.value.recoveryResult,
      recoveryDue: activeLine.value.recoveryDue || '',
    }
  if (name === 'attach')
    Object.assign(draft.value, {
      name: '合成补充证据.txt',
      category: '调查证据',
      content: '仅供演练的补充依据，请填写核对说明。',
    })
  if (name === 'share') draft.value.confirm = false
  baseline.value = JSON.stringify(draft.value)
  formError.value = ''
  modal.value = true
  focusDoc(
    (
      {
        record: 'investigate',
        submit: 'investigate',
        finance: 'finance',
        transfer_request: 'transfer',
        transfer_accept: 'transfer',
        transfer_reject: 'transfer',
        transfer_cancel: 'transfer',
        share: 'attachments',
        attach: 'attachments',
        collab_create: 'investigate',
        responsibility: 'investigate',
        reopen: 'close',
        edit: 'intake',
        preliminary: 'intake',
        lock: 'assign',
        unlock: 'assign',
      } as Record<string, string>
    )[name] || name,
  )
}
function fillExample() {
  Object.assign(draft.value, {
    description: '合成供应差异：核对业务处理与供应规则',
    facts: '已比对合成订单、原始票号和办理记录，来源一致。',
    cause: '供应规则版本与办理时理解存在差异，需核实责任。',
    proposal: '按证据选择申诉或差异登记，并安排预防整改。',
    conclusion: '当前事实与建议已整理，提交下一节点独立核对。',
    appealReason: '合成场景：证据充分，选择直接登记差异，不发起申诉。',
    financeReason: '合成场景：无需收付款，保留依据供审核。',
    diffType: '重复预定',
    diffSecond: '',
    attribution: '非人为/政策原因',
    differenceRecorded: true,
    differenceReason: 'DEMO-DIFF-001（模拟登记号）',
    remark: '此示例可修改；不能替代真实业务证据。',
  })
}
async function chooseAttachment(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    if (file.size > 2 * 1024 * 1024 || file.size === 0) throw Error('请选择非空、最多2MB的文件')
    const allowed = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf', 'text/plain']
    const mime = allowed.includes(file.type) ? file.type : 'application/octet-stream'
    const buffer = await file.arrayBuffer()
    let binary = ''
    const bytes = new Uint8Array(buffer)
    for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192))
    const content =
      mime === 'text/plain'
        ? (await file.text()).slice(0, 9000)
        : `本机文件：${file.name}（${file.size}字节）。仅保存在浏览器，未上传服务器。`
    Object.assign(draft.value, {
      name: file.name,
      mime,
      size: file.size,
      dataUrl: `data:${mime};base64,${btoa(binary)}`,
      content: content || '空文本文件',
    })
    formError.value = ''
  } catch (error) {
    formError.value = (error as Error).message
  }
}
function downloadAttachment(file: Evidence) {
  if (!file.dataUrl) {
    downloadText(file.name, file.content)
    return
  }
  const a = document.createElement('a')
  a.href = file.dataUrl
  a.download = file.name
  a.click()
}
function openIntake(copy = false) {
  action.value = 'intake'
  expected = state.value.version
  const base = current.value || state.value.cases[0]!
  const defaultSupplier = state.value.rules?.suppliers[0]
  draft.value = {
    admNo: `DEMO-ADM-${String(state.value.cases.length + 1).padStart(3, '0')}`,
    supplier: copy ? base.supplier : defaultSupplier?.name || '合成供应商 · 非真实业务',
    amount: copy ? base.amount : '1000.00',
    sourceType: '供应商',
    currency: copy ? base.currency || 'CNY' : 'CNY',
    rate: '',
    airline: 'XX',
    issuedOn: '2026-10-28',
    replyDue: '2026-11-05',
    description: copy ? base.description : '合成供应下发：请核实重复预定并反馈。',
    diffType: '重复预定',
    preliminary: false,
    remark: copy ? `引用 ${base.admNo}，不复制状态/附件授权/结论` : '',
    rows: copy
      ? base.lines
          .map((line) => `${line.orderNo}-新,${line.platform},${line.business},${line.amount},${line.pnr}`)
          .join('\n')
      : 'SYN-NEW-001,平台A,出票,600.00,DEMOA1\nSYN-NEW-002,平台B,退票,250.00,DEMOB2\nSYN-NEW-003,平台A,改签,150.00,DEMOA3',
    autoAssign: true,
  }
  baseline.value = JSON.stringify(draft.value)
  intakePreview.value = ''
  formError.value = ''
  modal.value = true
  focusDoc('intake')
}
function submitIntake() {
  if (actor.value !== 'coordinator') throw Error('仅协调人可接收')
  if (expected !== state.value.version) throw Error('版本变化，请重新核对')
  const value = draft.value
  if ((!value.preliminary && !value.admNo?.trim()) || !value.supplier?.trim()) throw Error('正式ADM号与供应商必填')
  if (state.value.cases.some((item) => item.admNo === value.admNo.trim() && item.supplier === value.supplier.trim()))
    throw Error('相同供应商已有此ADM号，请核对，不重复接收')
  const parent = prepareIntake(value, typeOptions.value)
  parent.lines.forEach((line) => {
    if (line.stage !== 'MATCH') line.owner = state.value.rules?.lead || 'lead'
  })
  const key = JSON.stringify(value)
  if (intakePreview.value !== key) {
    intakePreview.value = key
    notice.value = '预览通过，请核对后再次确认。'
    return
  }
  state.value.cases.push(parent)
  state.value.version++
  state.value.events.push({
    id: id(),
    at: state.value.clock,
    caseId: parent.id,
    lineId: '',
    actor: actor.value,
    action: 'publish',
    reason: value.remark || '模拟接收',
    before: '预览',
    after: '已接收',
    round: 1,
  })
  tasks(state.value)
    .filter((task) => task.caseId === parent.id)
    .forEach((task) =>
      state.value.notices.push({
        id: id(),
        recipient: task.owner,
        caseId: task.caseId,
        lineId: task.lineId,
        text: task.title,
        read: false,
      }),
    )
  openCase(parent.id)
  modal.value = false
  notice.value = '已保存到台账并生成组长接收或核实任务；可在本单继续切换下一处理人。'
}
function submitAction() {
  try {
    if (action.value === 'intake') {
      submitIntake()
      return
    }
    state.value =
      action.value === 'submit'
        ? submitProcessing(state.value, actor.value, contextCase, contextLine, draft.value, expected)
        : transition(state.value, actor.value, contextCase, contextLine, action.value, draft.value, expected)
    modal.value = false
    notice.value = `${actionNames[action.value]}成功（仅演练），任务与历史已更新。`
    if (activeLine.value) focusDoc(stageNode[activeLine.value.stage])
    if (current.value?.status === 'CLOSED' && action.value !== 'finance') {
      caseTab.value = 'close'
      focusDoc('close')
    }
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '演练操作失败，草稿保留'
  }
}
function entry(key: string) {
  if (!reviews.value[key]) reviews.value[key] = { status: '待验收', by: '', reason: '', at: '', checks: {}, notes: [] }
  return reviews.value[key]!
}
function toggleCheck(key: string, index: number) {
  const value = entry(key)
  value.checks[index] = !value.checks[index]
  if (value.status === '已通过') value.status = '待验收'
}
function reviewNode(status: string) {
  if (!reviewerName.value.trim()) {
    notice.value = '请填写评审人姓名'
    return
  }
  if (status === '已通过' && !doc.value.checks.every((_, index) => entry(doc.value.id).checks[index])) {
    notice.value = '请先逐项核对并勾选本页验收项；不自动替你通过'
    return
  }
  if (status !== '已通过' && !reviewReason.value.trim()) {
    notice.value = '需要修改或暂不做时，请说明原因'
    return
  }
  Object.assign(entry(doc.value.id), {
    status,
    by: reviewerName.value.trim(),
    reason: reviewReason.value,
    at: new Date().toISOString(),
  })
  notice.value = '页面评审已记录；整版开发批准需另行确认具体范围'
}
function addComment() {
  if (!reviewerName.value.trim() || !comment.value.trim()) {
    notice.value = '请填写姓名和意见'
    return
  }
  const value = entry(doc.value.id)
  value.notes.push({
    id: id(),
    by: reviewerName.value.trim(),
    at: new Date().toISOString(),
    text: comment.value.trim(),
  })
  value.status = '需修改'
  comment.value = ''
  notice.value = '意见已保存，请导出记录发给产品经理。不会自动修改业务规则。'
}
function approveVersion() {
  if (
    !approvalConfirm.value ||
    !approvalName.value.trim() ||
    !approvalReason.value.trim() ||
    !approvalIds.value.length ||
    approvalIds.value.some((key) => reviews.value[key]?.status !== '已通过')
  ) {
    notice.value = '请填写批准人、范围和说明，所选项须已通过，并明确勾选确认'
    return
  }
  approvals.value.push({
    id: id(),
    name: approvalName.value.trim(),
    ids: [...approvalIds.value],
    reason: approvalReason.value.trim(),
    version: VERSION,
    at: new Date().toISOString(),
  })
  approvalConfirm.value = false
  notice.value = '批准声明已记录在本机，请导出交接；不会自动启动开发或部署'
}
function packet() {
  return {
    kind: 'ADM_REVIEW_DEMO',
    version: VERSION,
    exportedAt: new Date().toISOString(),
    state: state.value,
    actor: actor.value,
    page: page.value,
    selectedCase: selectedCase.value,
    selectedLine: selectedLine.value,
    docId: docId.value,
    caseTab: caseTab.value,
    reviews: reviews.value,
    approvals: approvals.value,
    guideIndex: guideIndex.value,
  }
}
function downloadText(name: string, content: string, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function downloadReview() {
  downloadText(`${VERSION}-体验意见与验收记录.json`, JSON.stringify(packet(), null, 2), 'application/json')
  notice.value = '记录已请求下载。请确认文件保存成功，再发给产品经理；未上传到任何服务器。'
}
function validatePacket(value: any) {
  if (
    !value ||
    value.kind !== 'ADM_REVIEW_DEMO' ||
    value.version !== VERSION ||
    value.state?.schema !== 2 ||
    !Number.isSafeInteger(value.state.version) ||
    !Array.isArray(value.state.cases) ||
    value.state.cases.length > 100 ||
    !Array.isArray(value.state.events) ||
    !Array.isArray(value.state.notices) ||
    !roles.some((role) => role.id === value.actor) ||
    !value.reviews ||
    typeof value.reviews !== 'object' ||
    Array.isArray(value.reviews) ||
    typeof value.state.clock !== 'string' ||
    !/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(value.state.clock) ||
    !Array.isArray(value.approvals)
  )
    throw Error('记录格式或版本不匹配，未覆盖当前内容')
  for (const item of value.state.cases) {
    if (
      !item ||
      !item.id ||
      !['DRAFT', 'ACTIVE', 'CLOSED', 'VOID'].includes(item.status) ||
      !Array.isArray(item.lines) ||
      !Array.isArray(item.files) ||
      !item.remediation
    )
      throw Error('主单结构不完整')
    cents(item.amount)
    for (const line of item.lines) {
      if (
        !line ||
        !stageNames[line.stage as keyof typeof stageNames] ||
        !Array.isArray(line.evidence) ||
        !Array.isArray(line.appeals) ||
        !Array.isArray(line.collaborations)
      )
        throw Error('明细结构不完整')
      cents(line.amount)
    }
    for (const file of item.files)
      if (!file || !Array.isArray(file.shared) || typeof file.content !== 'string') throw Error('附件结构不完整')
  }
  for (const [key, review] of Object.entries(value.reviews) as [string, Review][]) {
    if (!nodes.some((node) => node.id === key) || !review || !Array.isArray(review.notes) || !review.checks)
      throw Error('验收项结构不完整')
    if (review.notes.some((note) => !note || typeof note.text !== 'string' || typeof note.by !== 'string'))
      throw Error('意见记录结构不完整')
  }
  if (
    value.approvals.some(
      (item: Approval) =>
        !item || !Array.isArray(item.ids) || item.ids.some((key) => !nodes.some((node) => node.id === key)),
    )
  )
    throw Error('批准范围结构不完整')
  if (
    value.state.notices.some(
      (item: Fields) => !item || typeof item.text !== 'string' || !roles.some((role) => role.id === item.recipient),
    )
  )
    throw Error('提醒结构不完整')
  if (
    value.state.events.some(
      (item: Fields) => !item || typeof item.caseId !== 'string' || typeof item.action !== 'string',
    )
  )
    throw Error('操作历史结构不完整')
  return value
}
function applyPacket(value: any) {
  validatePacket(value)
  state.value = value.state
  actor.value = value.actor
  page.value = value.page || 'overview'
  selectedCase.value = value.selectedCase || ''
  selectedLine.value = value.selectedLine || ''
  docId.value = value.docId || 'overview'
  caseTab.value = value.caseTab || 'detail'
  reviews.value = value.reviews
  approvals.value = value.approvals
  guideIndex.value = Math.max(
    0,
    Math.min(
      value.guideIndex || 0,
      (scenarios.find((item) => item.id === state.value.scenario)?.steps.length || 1) - 1,
    ),
  )
}
async function restoreFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    if (file.size > 2 * 1024 * 1024) throw Error('记录超过2MB，请核对文件')
    const value = validatePacket(JSON.parse(await file.text()))
    if (!confirm('导入将替换当前模拟进度和意见。建议先导出当前记录。是否继续？')) return
    applyPacket(value)
    notice.value = '记录已恢复；仍是本机模拟，不是正式业务数据。'
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '导入失败，原记录保留'
  } finally {
    input.value = ''
  }
}
function advanceClock() {
  const next = new Date(new Date(`${state.value.clock}:00+08:00`).getTime() + 3 * 86400000 + 8 * 3600000)
  state.value.clock = next.toISOString().slice(0, 16)
  state.value.version++
  notice.value = '演练时钟已前进3天（北京时间）；正式业务期限不因转交重置。'
}
function captureSnapshot() {
  snapshot.value = JSON.stringify(
    {
      label: '演练时点快照，非正式日报',
      clock: state.value.clock,
      version: state.value.version,
      scope: actor.value,
      people: reportPeople.value.map((person) => ({
        name: person.name,
        tasks: tasks(state.value).filter((task) => task.owner === person.id).length,
      })),
      limitations: ['无完整自然日历史', '无批准绩效口径', '不把申诉成功金额当到账'],
    },
    null,
    2,
  )
}
function detach() {
  child = window.open(`${location.href.split('#')[0]}#prd`, 'adm-review-prd')
  if (!child) {
    notice.value = '浏览器阻止新窗口，请允许本页面弹窗，或继续使用左右分屏。'
    return
  }
  notice.value = '右侧PRD已请求独立窗口。仅同一浏览器窗口联动，不是多人共享。'
}
function broadcast() {
  if (receiving) return
  // Vue proxies are not structured-cloneable; only send plain versioned JSON to known windows.
  const data = JSON.parse(JSON.stringify({ type: 'adm-review-sync', value: packet() }))
  try {
    const send = (target: Window | null) => {
      if (!target || target.closed) return
      if (location.origin === 'null' && target.location.href.split('#')[0] !== location.href.split('#')[0]) return
      target.postMessage(data, location.origin === 'null' ? '*' : location.origin)
    }
    send(child)
    if (docOnly) send(window.opener)
  } catch {
    notice.value = '双窗口同步未成功；当前记录保留，请继续左右分屏并导出。'
  }
}
function receive(event: MessageEvent) {
  if (event.source !== child && !(docOnly && event.source === window.opener)) return
  if (event.origin !== location.origin) return
  if (event.data?.type === 'adm-review-ready') {
    broadcast()
    return
  }
  if (event.data?.type !== 'adm-review-sync') return
  try {
    receiving = true
    applyPacket(event.data.value)
  } catch {
    notice.value = '联动记录不兼容，未应用'
  } finally {
    queueMicrotask(() => {
      receiving = false
    })
  }
}
window.addEventListener('message', receive)
try {
  const saved = localStorage.getItem(STORAGE)
  if (saved) applyPacket(JSON.parse(saved))
} catch {
  notice.value = '本机缓存不可用或版本不兼容；请用顶部导出功能保留意见。'
}
watch(
  [state, actor, page, selectedCase, selectedLine, docId, caseTab, reviews, approvals, guideIndex],
  () => {
    try {
      localStorage.setItem(STORAGE, JSON.stringify(packet()))
    } catch {
      notice.value = '缓存保存失败，请立即导出记录以免丢失。'
    }
    broadcast()
  },
  { deep: true },
)
if (docOnly && window.opener)
  window.opener.postMessage({ type: 'adm-review-ready' }, location.origin === 'null' ? '*' : location.origin)
onBeforeUnmount(() => {
  window.removeEventListener('message', receive)
})
</script>
