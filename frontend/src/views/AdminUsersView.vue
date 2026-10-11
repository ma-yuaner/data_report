<template>
  <div class="page-wrap account-page">
    <div class="page-header access-header">
      <div><div class="page-eyebrow">ACCESS CONTROL</div><h1>账号与权限</h1><p>用角色定义稳定职责，用个人权限处理少量例外。</p></div>
      <a-space><a-button @click="load" :loading="loading"><ReloadOutlined />刷新</a-button><a-button type="primary" @click="openCreateAccount"><PlusOutlined />新增账号</a-button></a-space>
    </div>

    <div class="model-row">
      <div class="model-card"><SafetyCertificateOutlined class="model-icon" /><div><strong>权限分配原则</strong><p>先给账号分配岗位角色，再对个人做少量开启或关闭，避免每个账号从零配置。</p></div><div class="model-flow"><span>账号</span><i>→</i><span>岗位角色</span><i>→</i><span>个人微调</span></div></div>
      <div class="summary-strip"><div><strong>{{ users.length }}</strong><span>账号总数</span></div><div><strong>{{ activeRoles.length }}</strong><span>启用角色</span></div><div><strong>{{ adminCount }}</strong><span>系统管理员</span></div></div>
    </div>

    <a-tabs v-model:active-key="activeTab" class="access-tabs">
      <a-tab-pane key="accounts" tab="账号管理">
        <a-card class="panel-card toolbar-card"><div class="account-toolbar">
          <a-input v-model:value="filters.keyword" allow-clear placeholder="搜索姓名、账号或邮箱" class="search-input"><template #prefix><SearchOutlined /></template></a-input>
          <a-select v-model:value="filters.role" allow-clear placeholder="全部角色" class="filter-select" :options="roleFilterOptions" />
          <a-select v-model:value="filters.status" allow-clear placeholder="全部状态" class="filter-select" :options="statusOptions" />
          <span class="toolbar-count">共 {{ filteredUsers.length }} 个账号</span><a-button type="primary" @click="openCreateAccount"><PlusOutlined />新增账号</a-button>
        </div></a-card>

        <a-card class="panel-card section-gap account-list-card" :body-style="{ padding: 0 }">
          <a-table :columns="userColumns" :data-source="filteredUsers" :loading="loading" row-key="id" :pagination="{ pageSize: 15 }" :scroll="{ x: 1280 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'identity'"><div class="account-identity"><span class="account-avatar">{{ record.displayName.slice(0, 1) }}</span><span><strong>{{ record.displayName }}</strong><code>{{ record.username }} · {{ record.email }}</code></span></div></template>
              <template v-else-if="column.key === 'roles'"><a-space v-if="record.businessRoles?.length" :size="[4, 4]" wrap><a-tag v-for="role in record.businessRoles" :key="role.code" color="blue">{{ role.name }}</a-tag></a-space><span v-else class="role-empty">未分配岗位角色</span></template>
              <template v-else-if="column.key === 'access'">
                <div class="access-summary" v-if="record.isAdmin"><a-tag color="purple">全部菜单与功能</a-tag></div>
                <div class="access-summary" v-else><span>{{ record.menuCodes?.length || 0 }} 个菜单 · {{ record.permissions?.length || 0 }} 项功能</span><a-tag v-if="overrideCount(record, 'ALLOW')" color="orange">+{{ overrideCount(record, 'ALLOW') }} 个人开启</a-tag><a-tag v-if="overrideCount(record, 'DENY')" color="red">-{{ overrideCount(record, 'DENY') }} 个人关闭</a-tag></div>
              </template>
              <template v-else-if="column.key === 'status'"><span class="status-dot" :class="{ off: !record.isEnabled }">{{ record.isEnabled ? '已启用' : '已禁用' }}</span></template>
              <template v-else-if="column.key === 'password'"><a-tag v-if="record.mustChangePassword" color="orange">待首次改密</a-tag><span v-else>正常</span></template>
              <template v-else-if="column.key === 'actions'"><a-space :size="2" wrap>
                <a-button type="link" size="small" @click="openRoles(record)">分配角色</a-button><a-button type="link" size="small" @click="openPersonalPermissions(record)">个人权限</a-button>
                <a-dropdown><a-button type="link" size="small">更多<DownOutlined /></a-button><template #overlay><a-menu><a-menu-item @click="openEdit(record)">编辑资料</a-menu-item><a-menu-item @click="openReset(record)">重置密码</a-menu-item><a-menu-item @click="toggleEnabled(record)">{{ record.isEnabled ? '禁用账号' : '启用账号' }}</a-menu-item><a-menu-item @click="toggleAdmin(record)">{{ record.isAdmin ? '取消系统管理员' : '设为系统管理员' }}</a-menu-item><a-menu-item v-if="record.legacyMenuCodes?.length" danger @click="clearLegacyMenus(record)">清除历史直授权</a-menu-item></a-menu></template></a-dropdown>
              </a-space></template>
            </template>
          </a-table>
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="roles" tab="角色与功能">
        <a-card class="panel-card toolbar-card"><div class="role-toolbar"><div><strong>岗位角色模板</strong><p>一个角色对应一组稳定菜单和功能，修改后会同步影响已分配人员。</p></div><a-button type="primary" @click="openCreateRole"><PlusOutlined />新增角色</a-button></div></a-card>
        <div class="role-card-grid section-gap">
          <a-card v-for="role in roles" :key="role.code" class="role-card" :class="{ disabled: !role.isActive }">
            <div class="role-card-head"><span class="role-mark">{{ role.name.slice(0, 1) }}</span><div><strong>{{ role.name }}</strong><code>{{ role.code }}</code></div><a-tag :color="role.isActive ? 'green' : 'default'">{{ role.isActive ? '启用' : '停用' }}</a-tag></div>
            <p class="role-description">{{ role.description || '暂无岗位职责说明' }}</p>
            <div class="role-block"><label>可见菜单</label><div class="tag-list"><a-tag v-for="code in role.menuCodes" :key="code">{{ menuName(code) }}</a-tag><span v-if="!role.menuCodes?.length" class="role-empty">无菜单</span></div></div>
            <div class="role-block"><label>固定功能</label><div class="tag-list"><a-tag v-for="code in role.permissions" :key="code" color="blue">{{ permissionName(code) }}</a-tag><span v-if="!role.permissions?.length" class="role-empty">仅查看菜单</span></div></div>
            <div class="role-card-foot"><span>已分配 {{ role.userCount || 0 }} 人 · 全部业务数据</span><a-button type="primary" ghost size="small" @click="openEditRole(role)">编辑菜单与功能</a-button></div>
          </a-card>
        </div>
      </a-tab-pane>

      <a-tab-pane key="audit" tab="操作审计"><a-card title="登录与权限操作审计" class="panel-card"><a-table :columns="auditColumns" :data-source="audits" row-key="id" size="small" :pagination="{ pageSize: 20 }" :scroll="{ x: 860 }"><template #bodyCell="{ column, record }"><template v-if="column.key === 'success'"><a-tag :color="record.success ? 'green' : 'red'">{{ record.success ? '成功' : '失败' }}</a-tag></template><template v-else-if="column.key === 'createdAt'">{{ formatTime(record.createdAt) }}</template><template v-else-if="column.key === 'detail'"><code>{{ detailText(record.detail) }}</code></template></template></a-table></a-card></a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="createVisible" title="新增账号" width="760px" ok-text="创建账号" cancel-text="取消" :confirm-loading="creating" @ok="createAccount">
      <p class="modal-lead">账号创建后继承岗位角色权限，首次登录必须修改初始密码。</p><div class="section-heading"><strong>基本信息</strong><span>用于登录和识别账号归属</span></div>
      <a-form layout="vertical" class="two-column-form"><a-form-item label="姓名" required><a-input v-model:value="createForm.displayName" placeholder="请输入真实姓名" /></a-form-item><a-form-item label="登录账号" required><a-input v-model:value="createForm.username" placeholder="字母、数字、点、下划线或短横线" /></a-form-item><a-form-item label="邮箱" required><a-input v-model:value="createForm.email" placeholder="name@example.com" /></a-form-item><a-form-item label="初始密码" required><a-input-password v-model:value="createForm.initialPassword" placeholder="至少8位，同时包含字母和数字" /></a-form-item></a-form>
      <a-divider /><div class="section-heading"><strong>岗位角色</strong><span>可多选，权限自动合并；个人例外创建后再调整</span></div>
      <a-checkbox-group v-model:value="createForm.roleCodes" class="role-picker"><a-checkbox v-for="role in activeRoles" :key="role.code" :value="role.code" class="role-option"><span class="option-copy"><strong>{{ role.name }}</strong><small>{{ role.description }}</small><em>{{ role.menuCodes?.length || 0 }} 个菜单 · {{ role.permissions?.length || 0 }} 项功能</em></span></a-checkbox></a-checkbox-group>
      <a-divider /><div class="admin-switch"><a-switch v-model:checked="createForm.isAdmin" /><span><strong>系统管理员</strong><small>拥有全部菜单、功能和账号管理权限，请谨慎授予。</small></span></div>
    </a-modal>

    <a-modal v-model:open="roleEditorVisible" :title="editingRoleCode ? `编辑角色：${roleForm.name}` : '新增角色'" width="1040px" :body-style="{ maxHeight: 'calc(100vh - 210px)', overflowY: 'auto' }" :mask-closable="false" @cancel="closeRoleEditor">
      <p class="modal-lead">角色定义岗位的固定菜单与功能；账号只需选择角色，少量例外再做个人微调。</p>
      <template v-if="!editingRoleCode"><div class="section-heading"><strong>1. 选择职责模板</strong><span>自动带出推荐字段、菜单和功能</span></div><div class="template-grid"><button v-for="item in roleTemplates" :key="item.key" class="template-button" :class="{ selected: selectedTemplate === item.key }" @click="applyRoleTemplate(item)"><strong>{{ item.name }}</strong><span>{{ item.summary }}</span></button></div><a-divider /></template>
      <div class="section-heading"><strong>{{ editingRoleCode ? '角色信息' : '2. 角色信息' }}</strong><span>角色名称面向业务人员，编码用于系统识别</span></div>
      <a-form layout="vertical" class="two-column-form"><a-form-item label="角色名称" required><a-input v-model:value="roleForm.name" placeholder="如：业务经理" /></a-form-item><a-form-item label="角色编码" required><a-input v-model:value="roleForm.roleCode" :disabled="Boolean(editingRoleCode)" placeholder="大写字母、数字和下划线" /></a-form-item><a-form-item label="岗位职责" required class="span-2"><a-textarea v-model:value="roleForm.description" :rows="2" placeholder="说明适用人员、负责环节和不能执行的操作" /></a-form-item></a-form>
      <a-divider /><div class="section-heading permission-heading"><div><strong>{{ editingRoleCode ? '固定菜单与功能' : '3. 固定菜单与功能' }}</strong><span>先选可见页面，再选页面内可执行功能；修改后同步影响全部已分配人员</span></div><div class="selection-summary"><a-tag color="blue">{{ roleForm.menuCodes.length }} 个菜单</a-tag><a-tag color="cyan">{{ roleForm.permissions.length }} 项功能</a-tag><a-tag v-if="editingRoleCode" color="orange">影响 {{ editingRole?.userCount || 0 }} 人</a-tag></div></div>
      <div class="permission-tree">
        <section v-for="group in menuGroups" :key="group.code" class="permission-group">
          <header>
            <a-checkbox :checked="isGroupFullySelected(group)" :indeterminate="isGroupPartlySelected(group)" @change="toggleMenuGroup(group, $event)">
              <span class="group-title">{{ group.name }}</span>
            </a-checkbox>
            <div class="group-actions"><small>{{ selectedGroupCount(group) }}/{{ group.items.length }} 个页面</small><a-button type="link" size="small" @click="selectMenuGroup(group)">全选</a-button><a-button type="link" size="small" danger @click="clearMenuGroup(group)">清空</a-button></div>
          </header>
          <div class="permission-page-list">
            <article v-for="item in group.items" :key="item.code" class="permission-page" :class="{ selected: roleForm.menuCodes.includes(item.code) }">
              <div class="permission-page-main">
                <a-checkbox :checked="roleForm.menuCodes.includes(item.code)" @change="toggleRoleMenu(item.code, $event)">
                  <span class="page-title">{{ item.name }}</span>
                </a-checkbox>
                <small>{{ item.description }}</small>
              </div>
              <div v-if="permissionsForMenu(item.code).length" class="page-functions">
                <span class="function-label">页面功能</span>
                <a-checkbox
                  v-for="permission in permissionsForMenu(item.code)"
                  :key="permission.code"
                  :checked="roleForm.permissions.includes(permission.code)"
                  class="function-check"
                  @change="toggleRolePermission(permission, $event)"
                >
                  <span><strong>{{ permission.name }}</strong><small>{{ permission.description }}</small></span>
                </a-checkbox>
              </div>
              <div v-else class="page-functions empty-functions"><span>该页面当前仅控制查看权限</span></div>
            </article>
          </div>
        </section>
      </div>
      <div class="admin-switch role-status"><a-switch v-model:checked="roleForm.isActive" /><span><strong>启用角色</strong><small>{{ roleForm.isActive ? '启用后可以分配给账号' : '停用后已分配账号将失去该角色权限' }}</small></span></div>
      <template #footer>
        <div class="role-editor-footer"><span>{{ editingRoleCode ? '修改角色会同步影响所有已分配账号' : '创建后可在账号管理中分配该角色' }}</span><a-space><a-button @click="resetRoleChanges">恢复原配置</a-button><a-button @click="closeRoleEditor">取消</a-button><a-button type="primary" :loading="roleEditorSaving" @click="confirmRoleSave">{{ editingRoleCode ? '保存修改' : '创建角色' }}</a-button></a-space></div>
      </template>
    </a-modal>

    <a-modal v-model:open="roleVisible" title="分配岗位角色" width="780px" ok-text="保存分配" cancel-text="取消" :confirm-loading="roleSaving" @ok="saveRoles">
      <p class="modal-lead">账号：{{ roleTarget?.displayName }}（{{ roleTarget?.username }}）。勾选角色只影响当前账号；编辑角色权限会同步影响全部已分配人员。</p>
      <div class="assignment-role-list">
        <div v-for="role in activeRoles" :key="role.code" class="assignment-role" :class="{ selected: selectedRoleCodes.includes(role.code) }">
          <a-checkbox :checked="selectedRoleCodes.includes(role.code)" @change="toggleAssignedRole(role.code, $event)">
            <span class="option-copy"><strong>{{ role.name }}</strong><small>{{ role.description }}</small><em>{{ role.menuCodes?.length || 0 }} 个菜单 · {{ role.permissions?.length || 0 }} 项功能</em></span>
          </a-checkbox>
          <a-button type="link" size="small" @click="editRoleFromAssignment(role)">编辑菜单与功能</a-button>
        </div>
      </div>
    </a-modal>

    <a-modal v-model:open="permissionVisible" title="个人权限微调" width="880px" ok-text="保存个人权限" cancel-text="取消" :confirm-loading="permissionSaving" @ok="savePersonalPermissions">
      <p class="modal-lead">账号：{{ permissionTarget?.displayName }}。有效权限 = 角色固定权限 ＋ 个人额外开启 － 个人单独关闭。</p><div class="personal-role-summary"><span><strong>岗位角色</strong><small>{{ permissionTarget?.businessRoles?.map(item => item.name).join('、') || '未分配角色' }}</small></span><a-tag color="blue">角色继承 {{ permissionTarget?.rolePermissions?.length || 0 }} 项</a-tag></div>
      <div class="permission-table"><div class="permission-row permission-head"><span>功能</span><span>角色状态</span><span>个人设置</span></div><div v-for="item in permissionCatalog" :key="item.code" class="permission-row"><span><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span><span><a-tag :color="permissionTarget?.rolePermissions?.includes(item.code) ? 'green' : 'default'">{{ permissionTarget?.rolePermissions?.includes(item.code) ? '角色已开启' : '角色未开启' }}</a-tag></span><a-radio-group v-model:value="personalOverrides[item.code]" button-style="solid" size="small"><a-radio-button value="INHERIT">继承</a-radio-button><a-radio-button value="ALLOW">开启</a-radio-button><a-radio-button value="DENY">关闭</a-radio-button></a-radio-group></div></div>
    </a-modal>

    <a-modal v-model:open="resetVisible" title="重置密码" ok-text="确认重置" cancel-text="取消" :confirm-loading="resetting" @ok="resetPassword"><p>账号：{{ resetTarget?.displayName }}（{{ resetTarget?.username }}）</p><a-input-password v-model:value="resetPasswordValue" placeholder="新初始密码（至少8位，含字母和数字）" /><p class="modal-lead">重置后现有会话立即失效，下次登录必须再次修改密码。</p></a-modal>
    <a-modal v-model:open="editVisible" title="修改账号资料" ok-text="保存" cancel-text="取消" :confirm-loading="editing" @ok="saveEdit"><a-form layout="vertical"><a-form-item label="姓名"><a-input v-model:value="editForm.displayName" /></a-form-item><a-form-item label="邮箱"><a-input v-model:value="editForm.email" /></a-form-item></a-form></a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { DownOutlined, PlusOutlined, ReloadOutlined, SafetyCertificateOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { authApi, type AuthAudit, type AuthUser, type BusinessRole, type FunctionPermission, type MenuPermission, type RolePayload } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

type OverrideState = 'INHERIT' | 'ALLOW' | 'DENY'
type RoleTemplate = { key: string; name: string; summary: string; code: string; description: string; menuCodes: string[]; permissions: string[] }
const roleTemplates: RoleTemplate[] = [
  { key: 'entry', name: '投放录入类', summary: '创建、编辑并提交投放机会', code: 'DATA_ENTRY_CUSTOM', description: '负责录入、编辑并提交智能投放机会，不参与审核与认领。', menuCodes: ['smart.placement.policies'], permissions: ['smart_placement.create', 'smart_placement.edit', 'smart_placement.delete', 'smart_placement.withdraw'] },
  { key: 'data', name: '数据运营类', summary: '数据审核与业务数据管理', code: 'DATA_MANAGER_CUSTOM', description: '负责审核数据口径、样本和预估价值，并作废尚未认领的无效任务。', menuCodes: ['smart.placement.policies'], permissions: ['smart_placement.review_data', 'smart_placement.cancel'] },
  { key: 'business', name: '业务审核类', summary: '任一业务经理完成政策审核', code: 'BUSINESS_MANAGER', description: '数据运营审核通过后，任一业务经理可审核政策可执行性与风险。', menuCodes: ['smart.placement.policies'], permissions: ['smart_placement.review_policy'] },
  { key: 'operator', name: '任务执行类', summary: '认领、登记投放并处理收单', code: 'SMART_BUSINESS_OPERATOR', description: '只处理已完成审核的任务，负责认领、登记政策ID并跟进命中订单。', menuCodes: ['smart.placement.policies', 'smart.placement.orders'], permissions: ['smart_placement.claim', 'smart_placement.execute', 'smart_placement.orders.attention'] },
]

const activeTab = ref('accounts')
const authStore = useAuthStore()
const users = ref<AuthUser[]>([]); const audits = ref<AuthAudit[]>([]); const roles = ref<BusinessRole[]>([]); const menuCatalog = ref<MenuPermission[]>([]); const permissionCatalog = ref<FunctionPermission[]>([])
const loading = ref(false); const creating = ref(false); const resetting = ref(false); const editing = ref(false); const roleSaving = ref(false); const roleEditorSaving = ref(false); const permissionSaving = ref(false)
const createVisible = ref(false); const resetVisible = ref(false); const editVisible = ref(false); const roleVisible = ref(false); const roleEditorVisible = ref(false); const permissionVisible = ref(false)
const resetTarget = ref<AuthUser | null>(null); const editTarget = ref<AuthUser | null>(null); const roleTarget = ref<AuthUser | null>(null); const permissionTarget = ref<AuthUser | null>(null)
const selectedRoleCodes = ref<string[]>([]); const resetPasswordValue = ref(''); const editingRoleCode = ref(''); const selectedTemplate = ref('business')
const returnToRoleAssignment = ref(false)
const filters = reactive({ keyword: '', role: undefined as string | undefined, status: undefined as string | undefined })
const createForm = reactive({ username: '', displayName: '', email: '', initialPassword: '', isAdmin: false, roleCodes: [] as string[] })
const editForm = reactive({ displayName: '', email: '' })
const roleForm = reactive<RolePayload>({ roleCode: '', name: '', description: '', isActive: true, menuCodes: [], permissions: [] })
const originalRole = ref<RolePayload>({ roleCode: '', name: '', description: '', isActive: true, menuCodes: [], permissions: [] })
const personalOverrides = reactive<Record<string, OverrideState>>({})
const activeRoles = computed(() => roles.value.filter(role => role.isActive)); const adminCount = computed(() => users.value.filter(user => user.isAdmin).length)
const editingRole = computed(() => roles.value.find(role => role.code === editingRoleCode.value))
const roleFilterOptions = computed(() => activeRoles.value.map(role => ({ value: role.code, label: role.name }))); const statusOptions = [{ value: 'enabled', label: '已启用' }, { value: 'disabled', label: '已禁用' }]
const filteredUsers = computed(() => users.value.filter(user => { const keyword = filters.keyword.trim().toLowerCase(); return (!keyword || [user.displayName, user.username, user.email].some(value => value.toLowerCase().includes(keyword))) && (!filters.role || user.businessRoles?.some(role => role.code === filters.role)) && (!filters.status || (filters.status === 'enabled' ? user.isEnabled : !user.isEnabled)) }))
const userColumns = [{ title: '账号', key: 'identity', width: 245 }, { title: '岗位角色', key: 'roles', width: 240 }, { title: '有效权限', key: 'access', width: 240 }, { title: '状态', key: 'status', width: 95 }, { title: '密码状态', key: 'password', width: 110 }, { title: '操作', key: 'actions', width: 270 }]
const auditColumns = [{ title: '时间', key: 'createdAt', width: 170 }, { title: '账号', dataIndex: 'username', width: 120 }, { title: '动作', dataIndex: 'action', width: 180 }, { title: '结果', key: 'success', width: 80 }, { title: 'IP', dataIndex: 'ipAddress', width: 140 }, { title: '详情', key: 'detail', width: 360 }]
type MenuGroup = { code: string; name: string; items: MenuPermission[] }
const menuGroups = computed<MenuGroup[]>(() => {
  const groups = new Map<string, MenuGroup>()
  for (const item of menuCatalog.value) {
    const current = groups.get(item.groupCode) || { code: item.groupCode, name: item.groupName, items: [] }
    current.items.push(item)
    groups.set(item.groupCode, current)
  }
  return [...groups.values()]
})

const load = async () => { loading.value = true; try { ;[users.value, audits.value, roles.value, menuCatalog.value, permissionCatalog.value] = await Promise.all([authApi.users(), authApi.audits(), authApi.roles(), authApi.menuCatalog(), authApi.permissionCatalog()]) } catch (error) { message.error(error instanceof Error ? error.message : '账号与权限数据加载失败') } finally { loading.value = false } }
const openCreateAccount = () => { Object.assign(createForm, { username: '', displayName: '', email: '', initialPassword: '', isAdmin: false, roleCodes: [] }); createVisible.value = true }
const createAccount = async () => { creating.value = true; try { await authApi.createUser({ ...createForm, roleCodes: [...createForm.roleCodes] }); message.success('账号创建成功，角色权限已生效'); createVisible.value = false; await load() } catch (error) { message.error(error instanceof Error ? error.message : '创建失败') } finally { creating.value = false } }
const update = async (record: AuthUser, payload: { displayName?: string; email?: string; isEnabled?: boolean; isAdmin?: boolean }) => { try { await authApi.updateUser(record.id, payload); message.success('账号已更新'); await load() } catch (error) { message.error(error instanceof Error ? error.message : '更新失败') } }
const toggleEnabled = (record: AuthUser) => Modal.confirm({ title: `${record.isEnabled ? '禁用' : '启用'}账号`, content: record.isEnabled ? '禁用后该账号现有会话将立即失效。' : '确认恢复该账号登录？', onOk: () => update(record, { isEnabled: !record.isEnabled }) })
const toggleAdmin = (record: AuthUser) => Modal.confirm({ title: '调整系统管理员', content: `确认${record.isAdmin ? '取消' : '授予'}该账号系统管理员权限？`, onOk: () => update(record, { isAdmin: !record.isAdmin }) })
const clearLegacyMenus = (record: AuthUser) => Modal.confirm({ title: '清除历史菜单直授权', content: '清除后，该账号只保留角色和个人功能产生的菜单。', onOk: async () => { await authApi.updateMenus(record.id, []); message.success('历史直授权已清除'); await load() } })
const openReset = (record: AuthUser) => { resetTarget.value = record; resetPasswordValue.value = ''; resetVisible.value = true }; const openEdit = (record: AuthUser) => { editTarget.value = record; Object.assign(editForm, { displayName: record.displayName, email: record.email }); editVisible.value = true }
const openRoles = (record: AuthUser) => { roleTarget.value = record; selectedRoleCodes.value = (record.businessRoles || []).map(role => role.code); roleVisible.value = true }
const saveRoles = async () => { if (!roleTarget.value) return; roleSaving.value = true; try { await authApi.updateBusinessRoles(roleTarget.value.id, selectedRoleCodes.value); message.success('岗位角色已更新'); roleVisible.value = false; await load() } catch (error) { message.error(error instanceof Error ? error.message : '角色更新失败') } finally { roleSaving.value = false } }
const toggleAssignedRole = (roleCode: string, event: { target?: { checked?: boolean } }) => {
  if (eventChecked(event)) selectedRoleCodes.value = [...new Set([...selectedRoleCodes.value, roleCode])]
  else selectedRoleCodes.value = selectedRoleCodes.value.filter(code => code !== roleCode)
}
const openPersonalPermissions = (record: AuthUser) => { permissionTarget.value = record; for (const item of permissionCatalog.value) personalOverrides[item.code] = record.permissionOverrides?.[item.code] || 'INHERIT'; permissionVisible.value = true }
const savePersonalPermissions = async () => { if (!permissionTarget.value) return; permissionSaving.value = true; try { const overrides: Record<string, 'ALLOW' | 'DENY'> = {}; for (const [code, state] of Object.entries(personalOverrides)) if (state === 'ALLOW' || state === 'DENY') overrides[code] = state; await authApi.updateUserPermissions(permissionTarget.value.id, overrides); message.success('个人权限已更新'); permissionVisible.value = false; await load() } catch (error) { message.error(error instanceof Error ? error.message : '个人权限更新失败') } finally { permissionSaving.value = false } }
const saveEdit = async () => { if (!editTarget.value) return; editing.value = true; try { await authApi.updateUser(editTarget.value.id, { ...editForm }); message.success('账号资料已更新'); editVisible.value = false; await load() } catch (error) { message.error(error instanceof Error ? error.message : '更新失败') } finally { editing.value = false } }
const resetPassword = async () => { if (!resetTarget.value) return; resetting.value = true; try { await authApi.resetPassword(resetTarget.value.id, resetPasswordValue.value); message.success('密码已重置'); resetVisible.value = false; await load() } catch (error) { message.error(error instanceof Error ? error.message : '重置失败') } finally { resetting.value = false } }
const resetRoleForm = () => Object.assign(roleForm, { roleCode: '', name: '', description: '', isActive: true, menuCodes: [], permissions: [] })
const applyRoleTemplate = (template: RoleTemplate) => { selectedTemplate.value = template.key; Object.assign(roleForm, { roleCode: template.code, name: template.name.replace('类', ''), description: template.description, isActive: true, menuCodes: [...template.menuCodes], permissions: [...template.permissions] }) }
const rolePayload = (): RolePayload => ({ ...roleForm, menuCodes: [...roleForm.menuCodes], permissions: [...roleForm.permissions] })
const rememberRole = () => { originalRole.value = rolePayload() }
const openCreateRole = () => { returnToRoleAssignment.value = false; editingRoleCode.value = ''; resetRoleForm(); applyRoleTemplate(roleTemplates[2]); rememberRole(); roleEditorVisible.value = true }
const openEditRole = (role: BusinessRole) => { returnToRoleAssignment.value = false; editingRoleCode.value = role.code; Object.assign(roleForm, { roleCode: role.code, name: role.name, description: role.description, isActive: Boolean(role.isActive), menuCodes: [...(role.menuCodes || [])], permissions: [...(role.permissions || [])] }); rememberRole(); roleEditorVisible.value = true }
const editRoleFromAssignment = (role: BusinessRole) => { roleVisible.value = false; openEditRole(role); returnToRoleAssignment.value = true }
const closeRoleEditor = () => { roleEditorVisible.value = false; if (returnToRoleAssignment.value) { returnToRoleAssignment.value = false; roleVisible.value = true } }
const resetRoleChanges = () => { Object.assign(roleForm, { ...originalRole.value, menuCodes: [...originalRole.value.menuCodes], permissions: [...originalRole.value.permissions] }) }
const permissionsForMenu = (menuCode: string) => permissionCatalog.value.filter(item => item.menuCode === menuCode)
const eventChecked = (event: { target?: { checked?: boolean } }) => Boolean(event?.target?.checked)
const selectedGroupCount = (group: MenuGroup) => group.items.filter(item => roleForm.menuCodes.includes(item.code)).length
const isGroupFullySelected = (group: MenuGroup) => selectedGroupCount(group) === group.items.length
const isGroupPartlySelected = (group: MenuGroup) => selectedGroupCount(group) > 0 && !isGroupFullySelected(group)
const removeMenusAndFunctions = (menuCodes: string[]) => {
  const removed = new Set(menuCodes)
  roleForm.menuCodes = roleForm.menuCodes.filter(code => !removed.has(code))
  roleForm.permissions = roleForm.permissions.filter(code => {
    const permission = permissionCatalog.value.find(item => item.code === code)
    return !permission || !removed.has(permission.menuCode)
  })
}
const confirmMenuRemoval = (menuCodes: string[], onConfirm: () => void) => {
  const functions = permissionCatalog.value.filter(item => menuCodes.includes(item.menuCode) && roleForm.permissions.includes(item.code))
  if (!functions.length) { onConfirm(); return }
  Modal.confirm({ title: '确认取消菜单权限', content: `取消后将同时移除 ${functions.length} 项页面功能：${functions.map(item => item.name).join('、')}`, okText: '确认取消', cancelText: '保留权限', okType: 'danger', onOk: onConfirm })
}
const toggleRoleMenu = (menuCode: string, event: { target?: { checked?: boolean } }) => {
  if (eventChecked(event)) { roleForm.menuCodes = [...new Set([...roleForm.menuCodes, menuCode])]; return }
  confirmMenuRemoval([menuCode], () => removeMenusAndFunctions([menuCode]))
}
const toggleMenuGroup = (group: MenuGroup, event: { target?: { checked?: boolean } }) => {
  const codes = group.items.map(item => item.code)
  if (eventChecked(event)) { roleForm.menuCodes = [...new Set([...roleForm.menuCodes, ...codes])]; return }
  confirmMenuRemoval(codes, () => removeMenusAndFunctions(codes))
}
const selectMenuGroup = (group: MenuGroup) => { roleForm.menuCodes = [...new Set([...roleForm.menuCodes, ...group.items.map(item => item.code)])] }
const clearMenuGroup = (group: MenuGroup) => { const codes = group.items.map(item => item.code); confirmMenuRemoval(codes, () => removeMenusAndFunctions(codes)) }
const toggleRolePermission = (permission: FunctionPermission, event: { target?: { checked?: boolean } }) => {
  if (eventChecked(event)) {
    roleForm.permissions = [...new Set([...roleForm.permissions, permission.code])]
    roleForm.menuCodes = [...new Set([...roleForm.menuCodes, permission.menuCode])]
  } else roleForm.permissions = roleForm.permissions.filter(code => code !== permission.code)
}
const changedNames = (before: string[], after: string[], resolver: (code: string) => string) => ({ added: after.filter(code => !before.includes(code)).map(resolver), removed: before.filter(code => !after.includes(code)).map(resolver) })
const persistRoleDefinition = async () => { roleEditorSaving.value = true; try { const payload = rolePayload(); if (editingRoleCode.value) await authApi.updateRole(editingRoleCode.value, payload); else await authApi.createRole(payload); message.success(editingRoleCode.value ? '角色配置已更新并对关联账号生效' : '角色已创建'); roleEditorVisible.value = false; await load(); try { await authStore.fetchMe(true) } catch { /* 当前管理员会话异常由全局认证处理 */ } if (returnToRoleAssignment.value) { returnToRoleAssignment.value = false; roleVisible.value = true } } catch (error) { message.error(error instanceof Error ? error.message : '角色保存失败') } finally { roleEditorSaving.value = false } }
const confirmRoleSave = () => {
  if (!roleForm.name.trim() || !roleForm.description.trim() || (!editingRoleCode.value && !roleForm.roleCode?.trim())) { message.warning('请先完整填写角色名称、编码和岗位职责'); return }
  const menuChanges = changedNames(originalRole.value.menuCodes, roleForm.menuCodes, menuName)
  const permissionChanges = changedNames(originalRole.value.permissions, roleForm.permissions, permissionName)
  const role = roles.value.find(item => item.code === editingRoleCode.value)
  const lines = [menuChanges.added.length ? `新增菜单：${menuChanges.added.join('、')}` : '', menuChanges.removed.length ? `移除菜单：${menuChanges.removed.join('、')}` : '', permissionChanges.added.length ? `新增功能：${permissionChanges.added.join('、')}` : '', permissionChanges.removed.length ? `移除功能：${permissionChanges.removed.join('、')}` : ''].filter(Boolean)
  Modal.confirm({ title: editingRoleCode.value ? `确认保存“${roleForm.name}”角色权限` : `确认创建“${roleForm.name}”角色`, content: `${lines.join('；') || '角色基础信息发生调整'}。${editingRoleCode.value ? `保存后将立即影响已分配的 ${role?.userCount || 0} 个账号。` : '创建后可在账号管理中进行分配。'}`, okText: '确认保存', cancelText: '继续检查', onOk: persistRoleDefinition })
}
const overrideCount = (record: AuthUser, effect: 'ALLOW' | 'DENY') => Object.values(record.permissionOverrides || {}).filter(item => item === effect).length
const menuName = (code: string) => menuCatalog.value.find(item => item.code === code)?.name || code; const permissionName = (code: string) => permissionCatalog.value.find(item => item.code === code)?.name || code
const formatTime = (value?: string | null) => value ? value.replace('T', ' ') : '—'; const detailText = (value: Record<string, unknown>) => Object.keys(value).length ? JSON.stringify(value) : '—'
onMounted(load)
</script>

<style scoped>
.account-page{max-width:1680px}.access-header{align-items:flex-start}.model-row{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(390px,.8fr);gap:14px;margin:18px 0 8px}.model-card,.summary-strip{border:1px solid #e3e8ef;border-radius:13px;background:#fff}.model-card{display:flex;align-items:center;gap:14px;min-height:80px;padding:15px 18px}.model-icon{flex:0 0 auto;padding:10px;border-radius:11px;color:#2e6dd6;background:#eaf2ff;font-size:20px}.model-card strong,.model-card p{display:block;margin:0}.model-card p{margin-top:5px;color:#748196;font-size:12px}.model-flow{display:flex;align-items:center;gap:7px;margin-left:auto;white-space:nowrap}.model-flow span{padding:6px 9px;border-radius:7px;color:#3a6da9;background:#f0f5fc;font-size:11px;font-weight:600}.model-flow i{color:#aab4c2;font-style:normal}.summary-strip{display:grid;grid-template-columns:repeat(3,1fr);align-items:center;padding:12px 0}.summary-strip div{text-align:center;border-right:1px solid #e7ebf0}.summary-strip div:last-child{border:0}.summary-strip strong,.summary-strip span{display:block}.summary-strip strong{font-size:23px}.summary-strip span{margin-top:5px;color:#78859a;font-size:11px}.access-tabs{margin-top:8px}.toolbar-card :deep(.ant-card-body){padding:13px 15px}.account-toolbar{display:flex;align-items:center;gap:10px}.search-input{width:280px}.filter-select{width:150px}.toolbar-count{margin-left:auto;color:#8894a6;font-size:12px}.account-list-card{overflow:hidden}.account-identity{display:flex;align-items:center;gap:10px}.account-identity>span:last-child{display:grid;gap:3px}.account-identity code{color:#8490a1;background:transparent;font-size:11px}.account-avatar,.role-mark{width:36px;height:36px;flex:0 0 auto;display:grid;place-items:center;border-radius:10px;color:#2b66c7;background:#eaf2ff;font-weight:700}.role-empty{color:#98a2b3;font-size:12px}.access-summary{display:flex;align-items:center;gap:5px;flex-wrap:wrap;color:#59677a;font-size:12px}.status-dot{display:inline-flex;align-items:center;gap:7px;font-size:12px}.status-dot:before{width:7px;height:7px;border-radius:50%;background:#20a16b;content:''}.status-dot.off:before{background:#a9b2bf}.role-toolbar{display:flex;align-items:center;justify-content:space-between}.role-toolbar p{margin:5px 0 0;color:#7c899c;font-size:12px}.role-card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.role-card.disabled{opacity:.68}.role-card-head{display:flex;align-items:center;gap:10px}.role-card-head>div{display:grid;gap:3px}.role-card-head code{color:#8a95a6;background:transparent;font-size:11px}.role-card-head>.ant-tag{margin-left:auto}.role-description{min-height:38px;margin:14px 0;color:#6e7b90;font-size:12px;line-height:1.6}.role-block{margin-top:12px}.role-block label{display:block;margin-bottom:7px;color:#8b97a8;font-size:11px}.tag-list{display:flex;flex-wrap:wrap;gap:4px;min-height:24px}.role-card-foot{display:flex;align-items:center;justify-content:space-between;margin-top:15px;padding-top:13px;border-top:1px solid #edf0f4;color:#7e8a9c;font-size:11px}.modal-lead{margin:0 0 18px;color:#69778c;line-height:1.6}.section-heading{display:flex;align-items:baseline;gap:9px;margin:4px 0 13px}.section-heading span{color:#8a96a8;font-size:11px}.two-column-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.two-column-form .span-2{grid-column:1/-1}.role-picker{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;width:100%}.role-option,.permission-option{display:flex;align-items:flex-start;gap:9px;margin:0;padding:12px 13px;border:1px solid #e0e6ee;border-radius:10px;background:#fafbfd;cursor:pointer;transition:border-color .18s,background .18s,box-shadow .18s}.role-option:hover,.permission-option:hover{border-color:#9bbaf0;background:#f6f9ff}.role-option.ant-checkbox-wrapper-checked,.permission-option.ant-checkbox-wrapper-checked{border-color:#5b8fe5;background:#edf4ff;box-shadow:inset 0 0 0 1px rgba(46,109,214,.12)}.role-option :deep(.ant-checkbox),.permission-option :deep(.ant-checkbox){margin-top:2px}.option-copy,.admin-switch>span{display:grid;gap:3px;min-width:0}.role-option small,.permission-option small,.admin-switch small{color:#7e8b9f;line-height:1.45}.role-option em{color:#2e6be6;font-size:11px;font-style:normal}.admin-switch{display:flex;align-items:flex-start;gap:10px}.template-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.template-button{padding:13px;border:1px solid #dfe4ec;border-radius:10px;color:#35445a;background:#fff;text-align:left;cursor:pointer}.template-button.selected{border-color:#6f9fe9;background:#f0f5ff;box-shadow:inset 0 0 0 1px rgba(43,109,229,.1)}.template-button strong,.template-button span{display:block}.template-button span{margin-top:5px;color:#8290a3;font-size:10px;line-height:1.45}.permission-layout{display:grid;grid-template-columns:1fr 1fr;gap:16px}.permission-layout h4{margin:0 0 10px;color:#4a586e;font-size:12px}.permission-grid{display:grid;gap:8px;width:100%}.role-status{margin-top:18px;padding:13px;border-radius:10px;background:#f7f9fc}.personal-role-summary{display:flex;justify-content:space-between;padding:13px 14px;border-radius:10px;background:#f2f6fc}.personal-role-summary>span{display:grid;gap:4px}.personal-role-summary small{color:#728097}.permission-table{margin-top:15px;border:1px solid #e1e6ed;border-radius:10px;overflow:hidden}.permission-row{display:grid;grid-template-columns:minmax(0,1fr) 130px 230px;align-items:center;min-height:55px;padding:9px 13px;border-top:1px solid #eef1f5}.permission-row:first-child{border-top:0}.permission-row>span:first-child{display:grid;gap:3px}.permission-row small{color:#8995a7;font-size:10px}.permission-head{min-height:40px;color:#748196;background:#f8fafc;font-size:11px;font-weight:600}@media(max-width:1180px){.model-row,.role-card-grid{grid-template-columns:1fr}.model-flow{display:none}}@media(max-width:760px){.two-column-form,.role-picker,.template-grid,.permission-layout{grid-template-columns:1fr}}
.permission-tree{display:grid;gap:12px;max-height:530px;padding-right:5px;overflow:auto}.permission-group{overflow:hidden;border:1px solid #dfe5ed;border-radius:12px;background:#fff}.permission-group>header{display:flex;align-items:center;justify-content:space-between;padding:12px 15px;border-bottom:1px solid #e8edf3;background:#f6f8fb}.permission-group>header small{color:#7e8a9d}.group-title{font-weight:700;color:#35445b}.permission-page-list{display:grid}.permission-page{display:grid;grid-template-columns:minmax(230px,.8fr) minmax(0,1.35fr);gap:18px;padding:13px 15px;border-top:1px solid #edf1f5}.permission-page:first-child{border-top:0}.permission-page.selected{background:#fbfdff}.permission-page-main{display:flex;flex-direction:column;align-items:flex-start;gap:5px}.permission-page-main small{padding-left:24px;color:#8793a5;line-height:1.45}.page-title{font-weight:600;color:#3b4a61}.page-functions{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}.function-label{padding-top:5px;color:#8994a6;font-size:10px}.function-check{margin:0!important;padding:5px 8px;border:1px solid #e2e7ee;border-radius:7px;background:#fff}.function-check>span:last-child{display:grid}.function-check strong{font-size:11px}.function-check small{color:#8b96a7;font-size:9px}.function-check.ant-checkbox-wrapper-checked{border-color:#8eb0eb;background:#eef4ff}.empty-functions{align-items:center;color:#9aa4b3;font-size:11px}
.permission-heading{align-items:center;justify-content:space-between}.permission-heading>div:first-child{display:flex;align-items:baseline;gap:9px}.selection-summary,.group-actions{display:flex;align-items:center;gap:3px}.assignment-role-list{display:grid;gap:10px}.assignment-role{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 14px;border:1px solid #e0e6ee;border-radius:11px;background:#fafbfd}.assignment-role.selected{border-color:#76a2e8;background:#f1f6ff}.assignment-role :deep(.ant-checkbox-wrapper){display:flex;align-items:flex-start;flex:1;gap:8px}.assignment-role :deep(.ant-checkbox){margin-top:3px}.assignment-role small{color:#7e8b9f;line-height:1.45}.assignment-role em{color:#2e6be6;font-size:11px;font-style:normal}.role-editor-footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.role-editor-footer>span{color:#8a6536;font-size:12px}.permission-tree{max-height:none;overflow:visible}.permission-group>header{padding:10px 15px}
@media(max-width:760px){.permission-page{grid-template-columns:1fr}.permission-heading,.role-editor-footer{align-items:flex-start;flex-direction:column}.assignment-role{align-items:flex-start}.assignment-role>a:last-child{white-space:nowrap}}
</style>
