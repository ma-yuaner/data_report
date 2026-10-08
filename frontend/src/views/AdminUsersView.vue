<template>
  <div class="page-wrap account-page">
    <div class="page-header">
      <div><div class="page-eyebrow">ACCESS CONTROL</div><h1>账号管理</h1><p>创建本地账号、控制启用状态、重置密码并查看登录审计。V1不包含部门数据权限。</p></div>
      <a-button @click="load" :loading="loading"><ReloadOutlined />刷新</a-button>
    </div>

    <a-card title="新增账号" class="panel-card section-gap">
      <div class="account-create-grid">
        <a-input v-model:value="createForm.username" placeholder="用户名（字母/数字/._-）" />
        <a-input v-model:value="createForm.displayName" placeholder="姓名" />
        <a-input-password v-model:value="createForm.initialPassword" placeholder="初始密码（至少8位，含字母和数字）" />
        <label class="account-switch"><a-switch v-model:checked="createForm.isAdmin" />管理员</label>
        <a-button type="primary" :loading="creating" @click="createAccount">创建账号</a-button>
      </div>
    </a-card>

    <a-card title="账号列表" class="panel-card section-gap">
      <a-table :columns="userColumns" :data-source="users" :loading="loading" row-key="id" :pagination="false" :scroll="{ x: 920 }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'identity'">
            <div class="account-identity"><strong>{{ record.displayName }}</strong><code>{{ record.username }}</code></div>
          </template>
          <template v-else-if="column.key === 'role'"><a-tag :color="record.isAdmin ? 'blue' : 'default'">{{ record.isAdmin ? '管理员' : '普通用户' }}</a-tag></template>
          <template v-else-if="column.key === 'status'"><a-tag :color="record.isEnabled ? 'green' : 'red'">{{ record.isEnabled ? '已启用' : '已禁用' }}</a-tag></template>
          <template v-else-if="column.key === 'password'"><a-tag v-if="record.mustChangePassword" color="orange">待首次改密</a-tag><span v-else>正常</span></template>
          <template v-else-if="column.key === 'createdAt'">{{ formatTime(record.createdAt) }}</template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" @click="toggleEnabled(record)">{{ record.isEnabled ? '禁用' : '启用' }}</a-button>
              <a-button size="small" @click="toggleAdmin(record)">{{ record.isAdmin ? '设为普通用户' : '设为管理员' }}</a-button>
              <a-button size="small" type="link" @click="openReset(record)">重置密码</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-card title="登录与账号操作审计" class="panel-card">
      <a-table :columns="auditColumns" :data-source="audits" row-key="id" size="small" :pagination="{ pageSize: 20 }" :scroll="{ x: 860 }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'success'"><a-tag :color="record.success ? 'green' : 'red'">{{ record.success ? '成功' : '失败' }}</a-tag></template>
          <template v-else-if="column.key === 'createdAt'">{{ formatTime(record.createdAt) }}</template>
          <template v-else-if="column.key === 'detail'"><code>{{ detailText(record.detail) }}</code></template>
        </template>
      </a-table>
    </a-card>

    <a-modal v-model:open="resetVisible" title="重置密码" ok-text="确认重置" cancel-text="取消" :confirm-loading="resetting" @ok="resetPassword">
      <p>账号：{{ resetTarget?.displayName }}（{{ resetTarget?.username }}）</p>
      <a-input-password v-model:value="resetPasswordValue" placeholder="新初始密码（至少8位，含字母和数字）" />
      <p class="account-modal-note">重置后该账号的所有登录会话立即失效，下次登录必须再次修改密码。</p>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { authApi, type AuthAudit, type AuthUser } from '@/api/auth'

const users = ref<AuthUser[]>([])
const audits = ref<AuthAudit[]>([])
const loading = ref(false)
const creating = ref(false)
const resetting = ref(false)
const resetVisible = ref(false)
const resetTarget = ref<AuthUser | null>(null)
const resetPasswordValue = ref('')
const createForm = reactive({ username: '', displayName: '', initialPassword: '', isAdmin: false })
const userColumns = [
  { title: '账号', key: 'identity', width: 190 }, { title: '角色', key: 'role', width: 100 },
  { title: '状态', key: 'status', width: 100 }, { title: '密码状态', key: 'password', width: 120 },
  { title: '创建时间', key: 'createdAt', width: 170 }, { title: '操作', key: 'actions', width: 330 },
]
const auditColumns = [
  { title: '时间', key: 'createdAt', width: 170 }, { title: '账号', dataIndex: 'username', width: 120 },
  { title: '动作', dataIndex: 'action', width: 150 }, { title: '结果', key: 'success', width: 80 },
  { title: 'IP', dataIndex: 'ipAddress', width: 140 }, { title: '详情', key: 'detail', width: 320 },
]

const load = async () => {
  loading.value = true
  try { [users.value, audits.value] = await Promise.all([authApi.users(), authApi.audits()]) }
  catch (error) { message.error(error instanceof Error ? error.message : '账号数据加载失败') }
  finally { loading.value = false }
}

const createAccount = async () => {
  creating.value = true
  try {
    await authApi.createUser({ ...createForm })
    Object.assign(createForm, { username: '', displayName: '', initialPassword: '', isAdmin: false })
    message.success('账号创建成功')
    await load()
  } catch (error) { message.error(error instanceof Error ? error.message : '创建失败') }
  finally { creating.value = false }
}

const update = async (record: AuthUser, payload: { isEnabled?: boolean; isAdmin?: boolean }) => {
  try { await authApi.updateUser(record.id, payload); message.success('账号已更新'); await load() }
  catch (error) { message.error(error instanceof Error ? error.message : '更新失败') }
}
const toggleEnabled = (record: AuthUser) => Modal.confirm({ title: `${record.isEnabled ? '禁用' : '启用'}账号`, content: record.isEnabled ? '禁用后该账号现有会话将立即失效。' : '确认恢复该账号登录？', onOk: () => update(record, { isEnabled: !record.isEnabled }) })
const toggleAdmin = (record: AuthUser) => Modal.confirm({ title: '调整管理员身份', content: `确认将该账号设为${record.isAdmin ? '普通用户' : '管理员'}？`, onOk: () => update(record, { isAdmin: !record.isAdmin }) })
const openReset = (record: AuthUser) => { resetTarget.value = record; resetPasswordValue.value = ''; resetVisible.value = true }
const resetPassword = async () => {
  if (!resetTarget.value) return
  resetting.value = true
  try { await authApi.resetPassword(resetTarget.value.id, resetPasswordValue.value); message.success('密码已重置'); resetVisible.value = false; await load() }
  catch (error) { message.error(error instanceof Error ? error.message : '重置失败') }
  finally { resetting.value = false }
}
const formatTime = (value?: string | null) => value ? value.replace('T', ' ') : '—'
const detailText = (value: Record<string, unknown>) => Object.keys(value).length ? JSON.stringify(value) : '—'
onMounted(load)
</script>
