<template>
  <div class="page-wrap account-page">
    <div class="page-header">
      <div>
        <div class="page-eyebrow">ACCESS CONTROL</div>
        <h1>账号与权限</h1>
        <p>账号只分配角色；菜单和功能权限统一由角色继承。系统管理员始终拥有全部权限。</p>
      </div>
      <a-button @click="load" :loading="loading"><ReloadOutlined />刷新</a-button>
    </div>

    <a-alert class="permission-model" type="info" show-icon>
      <template #message>当前权限模型</template>
      <template #description>
        <strong>账号 → 角色 → 菜单与功能</strong>。当前所有角色的数据范围均为“全部业务数据”，尚未启用按部门、平台或站点的行级数据隔离。
      </template>
    </a-alert>

    <a-tabs v-model:active-key="activeTab" class="access-tabs">
      <a-tab-pane key="accounts" tab="账号管理">
        <div class="summary-grid">
          <div><span>账号总数</span><strong>{{ users.length }}</strong></div>
          <div><span>启用账号</span><strong>{{ enabledUserCount }}</strong></div>
          <div><span>系统管理员</span><strong>{{ adminCount }}</strong></div>
          <div><span>可用角色</span><strong>{{ activeRoles.length }}</strong></div>
        </div>

        <a-card title="新增账号" class="panel-card section-gap">
          <a-form layout="vertical" class="account-create-form">
            <a-form-item label="用户名" required><a-input v-model:value="createForm.username" placeholder="字母、数字、点、下划线或短横线" /></a-form-item>
            <a-form-item label="姓名" required><a-input v-model:value="createForm.displayName" placeholder="请输入使用者姓名" /></a-form-item>
            <a-form-item label="邮箱" required><a-input v-model:value="createForm.email" placeholder="name@example.com" /></a-form-item>
            <a-form-item label="初始密码" required><a-input-password v-model:value="createForm.initialPassword" placeholder="至少8位，同时包含字母和数字" /></a-form-item>
            <a-form-item label="分配角色">
              <a-select v-model:value="createForm.roleCodes" mode="multiple" allow-clear placeholder="可多选，权限自动合并" :options="roleSelectOptions" />
            </a-form-item>
            <a-form-item label="系统管理员">
              <div class="admin-switch"><a-switch v-model:checked="createForm.isAdmin" /><span>拥有全部菜单、功能和账号管理权限</span></div>
            </a-form-item>
            <a-form-item class="create-action"><a-button type="primary" :loading="creating" @click="createAccount">创建账号</a-button></a-form-item>
          </a-form>
        </a-card>

        <a-card title="账号列表" class="panel-card section-gap">
          <a-table :columns="userColumns" :data-source="users" :loading="loading" row-key="id" :pagination="{ pageSize: 15 }" :scroll="{ x: 1320 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'identity'">
                <div class="account-identity"><strong>{{ record.displayName }}</strong><code>{{ record.username }} · {{ record.email }}</code></div>
              </template>
              <template v-else-if="column.key === 'admin'"><a-tag :color="record.isAdmin ? 'purple' : 'default'">{{ record.isAdmin ? '系统管理员' : '否' }}</a-tag></template>
              <template v-else-if="column.key === 'roles'">
                <a-space v-if="record.businessRoles?.length" :size="[4, 4]" wrap><a-tag v-for="role in record.businessRoles" :key="role.code" color="geekblue">{{ role.name }}</a-tag></a-space>
                <span v-else class="role-empty">未分配角色</span>
              </template>
              <template v-else-if="column.key === 'access'">
                <div class="access-summary">
                  <span v-if="record.isAdmin" class="access-all">全部菜单与功能</span>
                  <span v-else>{{ record.menuCodes?.length }} 个菜单 · {{ record.permissions?.length }} 项功能</span>
                  <a-tag v-if="record.legacyMenuCodes?.length" color="orange">含历史直授权</a-tag>
                </div>
              </template>
              <template v-else-if="column.key === 'status'"><a-tag :color="record.isEnabled ? 'green' : 'red'">{{ record.isEnabled ? '已启用' : '已禁用' }}</a-tag></template>
              <template v-else-if="column.key === 'password'"><a-tag v-if="record.mustChangePassword" color="orange">待首次改密</a-tag><span v-else>正常</span></template>
              <template v-else-if="column.key === 'createdAt'">{{ formatTime(record.createdAt) }}</template>
              <template v-else-if="column.key === 'actions'">
                <a-space wrap>
                  <a-button size="small" @click="openRoles(record)">分配角色</a-button>
                  <a-button size="small" @click="openEdit(record)">编辑资料</a-button>
                  <a-button size="small" @click="toggleEnabled(record)">{{ record.isEnabled ? '禁用' : '启用' }}</a-button>
                  <a-button size="small" @click="toggleAdmin(record)">{{ record.isAdmin ? '取消管理员' : '设为管理员' }}</a-button>
                  <a-button v-if="record.legacyMenuCodes?.length" size="small" danger @click="clearLegacyMenus(record)">清除直授权</a-button>
                  <a-button size="small" type="link" @click="openReset(record)">重置密码</a-button>
                </a-space>
              </template>
            </template>
          </a-table>
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="roles" tab="角色与权限">
        <a-card class="panel-card section-gap">
          <template #title><div class="card-title-row"><span>角色权限配置</span><small>角色可以同时控制菜单和页面内操作</small></div></template>
          <template #extra><a-button type="primary" @click="openCreateRole"><PlusOutlined />新增角色</a-button></template>
          <a-table :columns="roleColumns" :data-source="roles" :loading="loading" row-key="code" :pagination="false" :scroll="{ x: 1240 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'role'">
                <div class="role-name"><strong>{{ record.name }}</strong><code>{{ record.code }}</code><small>{{ record.description || '暂无说明' }}</small></div>
              </template>
              <template v-else-if="column.key === 'menus'">
                <a-space v-if="record.menuCodes?.length" :size="[4, 4]" wrap><a-tag v-for="code in record.menuCodes" :key="code">{{ menuName(code) }}</a-tag></a-space>
                <span v-else class="role-empty">无菜单</span>
              </template>
              <template v-else-if="column.key === 'permissions'">
                <a-space v-if="record.permissions?.length" :size="[4, 4]" wrap><a-tag v-for="code in record.permissions" :key="code" color="blue">{{ permissionName(code) }}</a-tag></a-space>
                <span v-else class="role-empty">仅查看菜单</span>
              </template>
              <template v-else-if="column.key === 'scope'"><a-tag color="cyan">全部业务数据</a-tag></template>
              <template v-else-if="column.key === 'status'"><a-tag :color="record.isActive ? 'green' : 'default'">{{ record.isActive ? '已启用' : '已停用' }}</a-tag></template>
              <template v-else-if="column.key === 'actions'"><a-button size="small" @click="openEditRole(record)">配置权限</a-button></template>
            </template>
          </a-table>
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="audit" tab="操作审计">
        <a-card title="登录与权限操作审计" class="panel-card section-gap">
          <a-table :columns="auditColumns" :data-source="audits" row-key="id" size="small" :pagination="{ pageSize: 20 }" :scroll="{ x: 860 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'success'"><a-tag :color="record.success ? 'green' : 'red'">{{ record.success ? '成功' : '失败' }}</a-tag></template>
              <template v-else-if="column.key === 'createdAt'">{{ formatTime(record.createdAt) }}</template>
              <template v-else-if="column.key === 'detail'"><code>{{ detailText(record.detail) }}</code></template>
            </template>
          </a-table>
        </a-card>
      </a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="resetVisible" title="重置密码" ok-text="确认重置" cancel-text="取消" :confirm-loading="resetting" @ok="resetPassword">
      <p>账号：{{ resetTarget?.displayName }}（{{ resetTarget?.username }}）</p>
      <a-input-password v-model:value="resetPasswordValue" placeholder="新初始密码（至少8位，含字母和数字）" />
      <p class="account-modal-note">重置后现有会话立即失效，下次登录必须再次修改密码。</p>
    </a-modal>

    <a-modal v-model:open="editVisible" title="修改账号资料" ok-text="保存" cancel-text="取消" :confirm-loading="editing" @ok="saveEdit">
      <a-form layout="vertical"><a-form-item label="姓名"><a-input v-model:value="editForm.displayName" /></a-form-item><a-form-item label="邮箱"><a-input v-model:value="editForm.email" /></a-form-item></a-form>
    </a-modal>

    <a-modal v-model:open="roleVisible" title="为账号分配角色" width="680px" ok-text="保存角色" cancel-text="取消" :confirm-loading="roleSaving" @ok="saveRoles">
      <p class="account-modal-note">账号：{{ roleTarget?.displayName }}（{{ roleTarget?.username }}）。可多选，菜单和功能权限自动取所有角色的并集。</p>
      <a-checkbox-group v-model:value="selectedRoleCodes" class="role-picker">
        <label v-for="role in activeRoles" :key="role.code" class="role-option">
          <a-checkbox :value="role.code" />
          <span><strong>{{ role.name }}</strong><small>{{ role.description }}</small><em>{{ role.menuCodes?.length }} 个菜单 · {{ role.permissions?.length }} 项功能</em></span>
        </label>
      </a-checkbox-group>
    </a-modal>

    <a-modal v-model:open="roleEditorVisible" :title="editingRoleCode ? '配置角色权限' : '新增角色'" width="820px" ok-text="保存角色" cancel-text="取消" :confirm-loading="roleEditorSaving" @ok="saveRoleDefinition">
      <a-form layout="vertical" class="role-form">
        <div class="role-form-grid">
          <a-form-item label="角色编码" required><a-input v-model:value="roleForm.roleCode" :disabled="Boolean(editingRoleCode)" placeholder="如 RISK_ANALYST" /></a-form-item>
          <a-form-item label="角色名称" required><a-input v-model:value="roleForm.name" placeholder="如 风控分析员" /></a-form-item>
        </div>
        <a-form-item label="角色说明"><a-textarea v-model:value="roleForm.description" :rows="2" placeholder="说明该角色适用人员及工作职责" /></a-form-item>
        <a-form-item label="角色状态"><div class="admin-switch"><a-switch v-model:checked="roleForm.isActive" /><span>{{ roleForm.isActive ? '启用后可分配给账号' : '停用后已分配账号立即失去该角色权限' }}</span></div></a-form-item>

        <div class="permission-section"><h3>菜单权限</h3><p>决定登录后左侧可以看到哪些业务模块。</p></div>
        <a-checkbox-group v-model:value="roleForm.menuCodes" class="permission-grid">
          <label v-for="item in menuCatalog" :key="item.code" class="permission-option">
            <a-checkbox :value="item.code" /><span><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span>
          </label>
        </a-checkbox-group>

        <div class="permission-section"><h3>功能权限</h3><p>决定进入菜单后可以执行哪些关键动作；没有功能权限时仍可查看已授权菜单。</p></div>
        <a-checkbox-group v-model:value="roleForm.permissions" class="permission-grid" @change="syncPermissionMenus">
          <label v-for="item in permissionCatalog" :key="item.code" class="permission-option">
            <a-checkbox :value="item.code" /><span><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span>
          </label>
        </a-checkbox-group>

        <a-alert type="warning" show-icon message="数据范围：全部业务数据" description="本版本尚未启用行级数据隔离。角色拥有菜单后，可以查看该菜单当前提供的全部业务数据。" />
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { authApi, type AuthAudit, type AuthUser, type BusinessRole, type FunctionPermission, type MenuPermission, type RolePayload } from '@/api/auth'

const activeTab = ref('accounts')
const users = ref<AuthUser[]>([])
const audits = ref<AuthAudit[]>([])
const roles = ref<BusinessRole[]>([])
const menuCatalog = ref<MenuPermission[]>([])
const permissionCatalog = ref<FunctionPermission[]>([])
const loading = ref(false)
const creating = ref(false)
const resetting = ref(false)
const editing = ref(false)
const roleSaving = ref(false)
const roleEditorSaving = ref(false)
const resetVisible = ref(false)
const editVisible = ref(false)
const roleVisible = ref(false)
const roleEditorVisible = ref(false)
const resetTarget = ref<AuthUser | null>(null)
const editTarget = ref<AuthUser | null>(null)
const roleTarget = ref<AuthUser | null>(null)
const selectedRoleCodes = ref<string[]>([])
const resetPasswordValue = ref('')
const editingRoleCode = ref('')
const createForm = reactive({ username: '', displayName: '', email: '', initialPassword: '', isAdmin: false, roleCodes: [] as string[] })
const editForm = reactive({ displayName: '', email: '' })
const roleForm = reactive<RolePayload>({ roleCode: '', name: '', description: '', isActive: true, menuCodes: [], permissions: [] })

const activeRoles = computed(() => roles.value.filter(role => role.isActive))
const enabledUserCount = computed(() => users.value.filter(user => user.isEnabled).length)
const adminCount = computed(() => users.value.filter(user => user.isAdmin).length)
const roleSelectOptions = computed(() => activeRoles.value.map(role => ({ value: role.code, label: role.name })))

const userColumns = [
  { title: '账号', key: 'identity', width: 210 }, { title: '系统管理员', key: 'admin', width: 110 },
  { title: '角色', key: 'roles', width: 260 }, { title: '继承权限', key: 'access', width: 170 },
  { title: '状态', key: 'status', width: 90 }, { title: '密码状态', key: 'password', width: 110 },
  { title: '创建时间', key: 'createdAt', width: 165 }, { title: '操作', key: 'actions', width: 440 },
]
const roleColumns = [
  { title: '角色', key: 'role', width: 250 }, { title: '菜单权限', key: 'menus', width: 260 },
  { title: '功能权限', key: 'permissions', width: 320 }, { title: '数据范围', key: 'scope', width: 130 },
  { title: '已分配', dataIndex: 'userCount', width: 80 }, { title: '状态', key: 'status', width: 90 },
  { title: '操作', key: 'actions', width: 110 },
]
const auditColumns = [
  { title: '时间', key: 'createdAt', width: 170 }, { title: '账号', dataIndex: 'username', width: 120 },
  { title: '动作', dataIndex: 'action', width: 160 }, { title: '结果', key: 'success', width: 80 },
  { title: 'IP', dataIndex: 'ipAddress', width: 140 }, { title: '详情', key: 'detail', width: 340 },
]

const load = async () => {
  loading.value = true
  try {
    [users.value, audits.value, roles.value, menuCatalog.value, permissionCatalog.value] = await Promise.all([
      authApi.users(), authApi.audits(), authApi.roles(), authApi.menuCatalog(), authApi.permissionCatalog(),
    ])
  } catch (error) { message.error(error instanceof Error ? error.message : '账号与权限数据加载失败') }
  finally { loading.value = false }
}

const createAccount = async () => {
  creating.value = true
  try {
    await authApi.createUser({ ...createForm, roleCodes: [...createForm.roleCodes] })
    Object.assign(createForm, { username: '', displayName: '', email: '', initialPassword: '', isAdmin: false, roleCodes: [] })
    message.success('账号创建成功，角色权限已生效')
    await load()
  } catch (error) { message.error(error instanceof Error ? error.message : '创建失败') }
  finally { creating.value = false }
}

const update = async (record: AuthUser, payload: { displayName?: string; email?: string; isEnabled?: boolean; isAdmin?: boolean }) => {
  try { await authApi.updateUser(record.id, payload); message.success('账号已更新'); await load() }
  catch (error) { message.error(error instanceof Error ? error.message : '更新失败') }
}
const toggleEnabled = (record: AuthUser) => Modal.confirm({ title: `${record.isEnabled ? '禁用' : '启用'}账号`, content: record.isEnabled ? '禁用后该账号现有会话将立即失效。' : '确认恢复该账号登录？', onOk: () => update(record, { isEnabled: !record.isEnabled }) })
const toggleAdmin = (record: AuthUser) => Modal.confirm({ title: '调整系统管理员', content: `确认${record.isAdmin ? '取消' : '授予'}该账号系统管理员权限？`, onOk: () => update(record, { isAdmin: !record.isAdmin }) })
const clearLegacyMenus = (record: AuthUser) => Modal.confirm({ title: '清除历史菜单直授权', content: '清除后，该账号只保留角色继承的菜单。此操作不会修改角色。', onOk: async () => { await authApi.updateMenus(record.id, []); message.success('历史直授权已清除'); await load() } })
const openReset = (record: AuthUser) => { resetTarget.value = record; resetPasswordValue.value = ''; resetVisible.value = true }
const openEdit = (record: AuthUser) => { editTarget.value = record; Object.assign(editForm, { displayName: record.displayName, email: record.email }); editVisible.value = true }
const openRoles = (record: AuthUser) => { roleTarget.value = record; selectedRoleCodes.value = (record.businessRoles || []).map(role => role.code); roleVisible.value = true }
const saveRoles = async () => {
  if (!roleTarget.value) return
  roleSaving.value = true
  try { await authApi.updateBusinessRoles(roleTarget.value.id, selectedRoleCodes.value); message.success('角色已分配，菜单与功能权限自动生效'); roleVisible.value = false; await load() }
  catch (error) { message.error(error instanceof Error ? error.message : '角色更新失败') }
  finally { roleSaving.value = false }
}
const saveEdit = async () => {
  if (!editTarget.value) return
  editing.value = true
  try { await authApi.updateUser(editTarget.value.id, { ...editForm }); message.success('账号资料已更新'); editVisible.value = false; await load() }
  catch (error) { message.error(error instanceof Error ? error.message : '更新失败') }
  finally { editing.value = false }
}
const resetPassword = async () => {
  if (!resetTarget.value) return
  resetting.value = true
  try { await authApi.resetPassword(resetTarget.value.id, resetPasswordValue.value); message.success('密码已重置'); resetVisible.value = false; await load() }
  catch (error) { message.error(error instanceof Error ? error.message : '重置失败') }
  finally { resetting.value = false }
}

const resetRoleForm = () => Object.assign(roleForm, { roleCode: '', name: '', description: '', isActive: true, menuCodes: [], permissions: [] })
const openCreateRole = () => { editingRoleCode.value = ''; resetRoleForm(); roleEditorVisible.value = true }
const openEditRole = (role: BusinessRole) => {
  editingRoleCode.value = role.code
  Object.assign(roleForm, { roleCode: role.code, name: role.name, description: role.description, isActive: Boolean(role.isActive), menuCodes: [...(role.menuCodes || [])], permissions: [...(role.permissions || [])] })
  roleEditorVisible.value = true
}
const syncPermissionMenus = () => {
  const required = permissionCatalog.value.filter(item => roleForm.permissions.includes(item.code)).map(item => item.menuCode)
  roleForm.menuCodes = [...new Set([...roleForm.menuCodes, ...required])]
}
const saveRoleDefinition = async () => {
  roleEditorSaving.value = true
  try {
    const payload: RolePayload = { ...roleForm, menuCodes: [...roleForm.menuCodes], permissions: [...roleForm.permissions] }
    if (editingRoleCode.value) await authApi.updateRole(editingRoleCode.value, payload)
    else await authApi.createRole(payload)
    message.success(editingRoleCode.value ? '角色权限已更新' : '角色已创建')
    roleEditorVisible.value = false
    await load()
  } catch (error) { message.error(error instanceof Error ? error.message : '角色保存失败') }
  finally { roleEditorSaving.value = false }
}

const menuName = (code: string) => menuCatalog.value.find(item => item.code === code)?.name || code
const permissionName = (code: string) => permissionCatalog.value.find(item => item.code === code)?.name || code
const formatTime = (value?: string | null) => value ? value.replace('T', ' ') : '—'
const detailText = (value: Record<string, unknown>) => Object.keys(value).length ? JSON.stringify(value) : '—'
onMounted(load)
</script>

<style scoped>
.account-page { max-width: 1680px; }
.permission-model { margin: 18px 0 6px; border-radius: 12px; }
.access-tabs { margin-top: 8px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 14px 0 18px; }
.summary-grid > div { display: grid; gap: 7px; padding: 16px 18px; border: 1px solid #e7ebf0; border-radius: 12px; background: #fff; }
.summary-grid span { color: #667085; font-size: 13px; }
.summary-grid strong { color: #172b4d; font-size: 25px; }
.account-create-form { display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 0 18px; align-items: end; }
.account-create-form :deep(.ant-form-item) { margin-bottom: 16px; }
.admin-switch { display: flex; align-items: center; gap: 10px; min-height: 32px; color: #667085; }
.create-action { display: flex; justify-content: flex-end; }
.account-identity, .role-name { display: grid; gap: 4px; }
.account-identity code, .role-name code { color: #667085; font-size: 12px; background: transparent; }
.role-name small { color: #7b8798; line-height: 1.45; }
.role-empty { color: #98a2b3; }
.access-all { color: #6941c6; font-weight: 600; }
.access-summary { display: grid; gap: 5px; justify-items: start; }
.card-title-row { display: flex; align-items: baseline; gap: 10px; }
.card-title-row small { color: #98a2b3; font-weight: 400; }
.account-modal-note { color: #667085; line-height: 1.6; }
.role-picker { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; width: 100%; margin-top: 14px; }
.role-option, .permission-option { display: flex; align-items: flex-start; gap: 10px; padding: 13px 14px; border: 1px solid #e1e7ef; border-radius: 10px; background: #f8fafc; cursor: pointer; }
.role-option > span, .permission-option > span { display: grid; gap: 3px; }
.role-option strong, .permission-option strong { color: #344054; }
.role-option small, .permission-option small { color: #7b8798; line-height: 1.45; }
.role-option em { color: #2e6be6; font-size: 12px; font-style: normal; }
.role-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.permission-section { margin: 8px 0 12px; }
.permission-section h3 { margin: 0 0 4px; color: #1d2939; }
.permission-section p { margin: 0; color: #7b8798; }
.permission-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; width: 100%; margin-bottom: 22px; }
@media (max-width: 1100px) { .account-create-form { grid-template-columns: repeat(2, minmax(220px, 1fr)); } }
@media (max-width: 760px) { .summary-grid, .account-create-form, .role-picker, .role-form-grid, .permission-grid { grid-template-columns: 1fr; } }
</style>
