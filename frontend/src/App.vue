<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  API_BASE_URL,
  ApiError,
  checkHealth,
  createDepartment,
  createEmployee,
  deleteDepartment,
  deleteDocument,
  deleteEmployee,
  getCurrentUser,
  login,
  logout,
  listDocuments,
  listDepartments,
  listEmployees,
  streamChat,
  uploadDocument,
  updateDepartment,
  updateEmployee,
  type AuthUser,
  type Department,
  type KnowledgeDocument,
} from './api'

type Message = {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
}

const welcomeMessage = '你好，我是企业知识库客服。你可以询问员工制度、工作流程和新员工入职相关内容。'
const messages = ref<Message[]>([
  {
    role: 'assistant',
    content: welcomeMessage,
  },
])
const question = ref('')
const currentUser = ref<AuthUser | null>(null)
const isCheckingAuth = ref(true)
const loginUsername = ref('')
const loginPassword = ref('')
const isLoggingIn = ref(false)
const newEmployeeUsername = ref('')
const newEmployeePassword = ref('')
const isCreatingEmployee = ref(false)
const newDepartmentName = ref('')
const isCreatingDepartment = ref(false)
const departments = ref<Department[]>([])
const employees = ref<AuthUser[]>([])
const adminView = ref<'chat' | 'manage'>('chat')
const managementTab = ref<'departments' | 'employees' | 'documents'>('departments')
const editingDepartmentId = ref<string | null>(null)
const editingDepartmentName = ref('')
const editingEmployeeId = ref<string | null>(null)
const editingEmployeeUsername = ref('')
const editingEmployeeDepartmentId = ref('default')
const editingEmployeePassword = ref('')
const uploadDepartmentId = ref('default')
const employeeDepartmentId = ref('default')
const isSending = ref(false)
const streamingAnswer = ref('')
const streamingSources = ref<string[]>([])
const isUploading = ref(false)
const documents = ref<KnowledgeDocument[]>([])
const selectedFile = ref<File | null>(null)
const documentId = ref('')
const notice = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const health = ref<'checking' | 'ok' | 'error'>('checking')
const healthText = ref('检查中')
let healthTimer: number | undefined

const canSend = computed(() => Boolean(currentUser.value && question.value.trim() && !isSending.value))
const canUpload = computed(() => Boolean(isAdmin.value && selectedFile.value && documentId.value.trim() && !isUploading.value))
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const isChatView = computed(() => Boolean(currentUser.value && (!isAdmin.value || adminView.value === 'chat')))

function setNotice(type: 'success' | 'error', text: string) {
  notice.value = { type, text }
  window.setTimeout(() => {
    if (notice.value?.text === text) notice.value = null
  }, 4500)
}

function clearSession() {
  currentUser.value = null
  documents.value = []
  departments.value = []
  employees.value = []
}

function handleUnauthorized(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 401) return false
  clearSession()
  setNotice('error', '登录已失效，请重新登录。')
  return true
}

async function refreshDocuments() {
  if (!currentUser.value) return
  try {
    const result = await listDocuments()
    documents.value = result.docs
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '读取文档列表失败')
  }
}

async function refreshManagementData() {
  if (!isAdmin.value) return
  try {
    const [departmentList, employeeList, documentList] = await Promise.all([
      listDepartments(),
      listEmployees(),
      listDocuments(),
    ])
    departments.value = departmentList
    employees.value = employeeList
    documents.value = documentList.docs
    const fallbackDepartmentId = departmentList[0]?.id || 'default'
    if (!departmentList.some((department) => department.id === uploadDepartmentId.value)) uploadDepartmentId.value = fallbackDepartmentId
    if (!departmentList.some((department) => department.id === employeeDepartmentId.value)) employeeDepartmentId.value = fallbackDepartmentId
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '读取管理数据失败')
  }
}

async function refreshHealth() {
  health.value = 'checking'
  healthText.value = '检查中'
  try {
    await checkHealth()
    health.value = 'ok'
    healthText.value = '服务正常'
  } catch {
    health.value = 'error'
    healthText.value = '服务离线'
  }
}

async function sendQuestion() {
  const content = question.value.trim()
  if (!content || isSending.value) return

  messages.value.push({ role: 'user', content })
  question.value = ''
  isSending.value = true
  streamingAnswer.value = ''
  streamingSources.value = []

  try {
    await streamChat(content, {
      onToken: (token) => {
        const candidate = streamingAnswer.value + token
        streamingAnswer.value = candidate.trim() ? candidate.trimStart() : ''
      },
      onSources: (sources) => { streamingSources.value = sources },
    })
    messages.value.push({
      role: 'assistant',
      content: streamingAnswer.value.trim(),
      sources: streamingSources.value,
    })
  } catch (error) {
    if (handleUnauthorized(error)) {
      messages.value.push({ role: 'assistant', content: '登录已失效，请重新登录后继续提问。' })
      return
    }
    messages.value.push({
      role: 'assistant',
      content: error instanceof Error ? `暂时无法回答：${error.message}` : '暂时无法回答，请稍后重试。',
    })
  } finally {
    isSending.value = false
    streamingAnswer.value = ''
    streamingSources.value = []
  }
}

function handleQuestionKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void sendQuestion()
  }
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  input.value = ''
  selectedFile.value = file
  if (file) {
    documentId.value = file.name.replace(/\.pdf$/i, '').replace(/[^\w\u4e00-\u9fff-]+/g, '_').slice(0, 128)
    notice.value = null
  }
}

async function handleUpload() {
  if (!isAdmin.value) {
    setNotice('error', '只有管理员可以导入文档。')
    return
  }
  if (!selectedFile.value || !documentId.value.trim() || isUploading.value) return
  if (!selectedFile.value.name.toLowerCase().endsWith('.pdf')) {
    setNotice('error', '只能上传 PDF 文件。')
    return
  }

  isUploading.value = true
  try {
    const result = await uploadDocument(
      documentId.value.trim(),
      selectedFile.value,
      uploadDepartmentId.value,
    )
    const data = result.data
    setNotice('success', `文档${data.status === 'skipped' ? '无需更新' : '导入完成'}：${data.doc_id}`)
    selectedFile.value = null
    documentId.value = ''
    await refreshManagementData()
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '文档导入失败')
  } finally {
    isUploading.value = false
  }
}

async function handleDelete(document: KnowledgeDocument) {
  if (!isAdmin.value) {
    setNotice('error', '只有管理员可以删除文档。')
    return
  }
  if (!window.confirm(`确定删除“${document.doc_id}”吗？删除后将无法检索这份文档。`)) return
  try {
    await deleteDocument(document.doc_id)
    setNotice('success', `已删除文档：${document.doc_id}`)
    await refreshManagementData()
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '删除文档失败')
  }
}

function clearConversation() {
  messages.value = [{
    role: 'assistant',
    content: '对话已清空。你可以继续询问企业制度和工作流程。',
  }]
}

function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function departmentLabel(departmentId?: string) {
  if (!departmentId) return '未分配部门'
  return departments.value.find((department) => department.id === departmentId)?.name || '未知部门'
}

async function handleLogin() {
  const username = loginUsername.value.trim()
  if (!username || !loginPassword.value || isLoggingIn.value) return
  isLoggingIn.value = true
  try {
    await login(username, loginPassword.value)
    // 登录响应返回用户信息并不等于浏览器已经保存 Cookie，立即回读会话确认两者一致。
    const authenticatedUser = await getCurrentUser()
    currentUser.value = authenticatedUser
    messages.value = [{ role: 'assistant', content: welcomeMessage }]
    loginPassword.value = ''
    setNotice('success', `欢迎，${authenticatedUser.username}`)
    if (authenticatedUser.role === 'admin') await refreshManagementData()
    else await refreshDocuments()
  } catch (error) {
    clearSession()
    setNotice('error', error instanceof Error ? error.message : '登录失败')
  } finally {
    isLoggingIn.value = false
  }
}

async function handleCreateEmployee() {
  const username = newEmployeeUsername.value.trim()
  if (!username || !newEmployeePassword.value || isCreatingEmployee.value) return
  isCreatingEmployee.value = true
  try {
    const user = await createEmployee(
      username,
      newEmployeePassword.value,
      employeeDepartmentId.value,
    )
    newEmployeeUsername.value = ''
    newEmployeePassword.value = ''
    setNotice('success', `员工账号 ${user.username} 已创建`)
    await refreshManagementData()
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '创建员工账号失败')
  } finally {
    isCreatingEmployee.value = false
  }
}

async function handleCreateDepartment() {
  const name = newDepartmentName.value.trim()
  if (!name || isCreatingDepartment.value) return
  isCreatingDepartment.value = true
  try {
    const department = await createDepartment(name)
    departments.value = [...departments.value, department].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
    uploadDepartmentId.value = department.id
    employeeDepartmentId.value = department.id
    newDepartmentName.value = ''
    setNotice('success', `部门 ${department.name} 已创建`)
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '创建部门失败')
  } finally {
    isCreatingDepartment.value = false
  }
}

function beginEditDepartment(department: Department) {
  editingDepartmentId.value = department.id
  editingDepartmentName.value = department.name
}

async function saveDepartment(department: Department) {
  const name = editingDepartmentName.value.trim()
  if (!name) return
  try {
    await updateDepartment(department.id, name)
    editingDepartmentId.value = null
    await refreshManagementData()
    setNotice('success', '部门名称已更新')
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '修改部门失败')
  }
}

async function handleDeleteDepartment(department: Department) {
  if (department.id === 'default') {
    setNotice('error', '默认部门不可删除')
    return
  }
  if (!window.confirm(`确定删除部门“${department.name}”吗？部门必须没有员工和知识库文档。`)) return
  try {
    await deleteDepartment(department.id)
    await refreshManagementData()
    setNotice('success', `部门 ${department.name} 已删除`)
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '删除部门失败')
  }
}

function beginEditEmployee(employee: AuthUser) {
  editingEmployeeId.value = employee.id
  editingEmployeeUsername.value = employee.username
  editingEmployeeDepartmentId.value = employee.department_id || 'default'
  editingEmployeePassword.value = ''
}

async function saveEmployee(employee: AuthUser) {
  const username = editingEmployeeUsername.value.trim()
  if (!username) return
  if (editingEmployeePassword.value && editingEmployeePassword.value.length < 8) {
    setNotice('error', '新密码至少需要 8 位')
    return
  }
  try {
    await updateEmployee(
      employee.id,
      username,
      editingEmployeeDepartmentId.value,
      editingEmployeePassword.value || undefined,
    )
    editingEmployeeId.value = null
    editingEmployeePassword.value = ''
    await refreshManagementData()
    setNotice('success', `员工账号 ${username} 已更新`)
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '修改员工失败')
  }
}

async function handleDeleteEmployee(employee: AuthUser) {
  if (!window.confirm(`确定删除员工账号“${employee.username}”吗？该员工将立即退出登录，对话记忆也会清除。`)) return
  try {
    await deleteEmployee(employee.id)
    await refreshManagementData()
    setNotice('success', `员工账号 ${employee.username} 已删除`)
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '删除员工失败')
  }
}

async function handleLogout() {
  try {
    await logout()
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : '退出登录失败')
  } finally {
    currentUser.value = null
    documents.value = []
    departments.value = []
    employees.value = []
    adminView.value = 'chat'
    messages.value = [{ role: 'assistant', content: welcomeMessage }]
  }
}

async function restoreSession() {
  isCheckingAuth.value = true
  try {
    currentUser.value = await getCurrentUser()
    if (currentUser.value.role === 'admin') {
      await refreshManagementData()
    } else {
      await refreshDocuments()
    }
  } catch {
    currentUser.value = null
  } finally {
    isCheckingAuth.value = false
  }
}

onMounted(() => {
  void restoreSession()
  void refreshHealth()
  healthTimer = window.setInterval(() => void refreshHealth(), 30000)
})

onBeforeUnmount(() => {
  if (healthTimer) window.clearInterval(healthTimer)
})
</script>

<template>
  <div class="app-shell" :class="{ 'chat-active': isChatView }">
    <header class="topbar">
      <div class="brand-block">
        <div class="brand-mark">知</div>
        <div>
          <p class="eyebrow">WORKSPACE KNOWLEDGE</p>
          <h1>企业知识库客服</h1>
        </div>
      </div>
      <nav v-if="isAdmin" class="top-navigation" aria-label="管理员导航">
        <button :class="{ active: adminView === 'chat' }" @click="adminView = 'chat'">问答工作台</button>
        <button :class="{ active: adminView === 'manage' }" @click="adminView = 'manage'">管理中心</button>
      </nav>
      <div class="topbar-meta">
        <span class="api-address">API · {{ API_BASE_URL }}</span>
        <span v-if="currentUser" class="user-pill">
          {{ currentUser.username }} · {{ isAdmin ? '管理员' : (currentUser.department_name || '未分配部门') }}
        </span>
        <button v-if="currentUser" class="text-button" @click="handleLogout">退出</button>
        <span class="health-pill" :class="`health-${health}`">
          <span class="health-dot"></span>{{ healthText }}
        </span>
      </div>
    </header>

    <main v-if="isCheckingAuth" class="auth-state">正在检查登录状态…</main>

    <main v-else-if="!currentUser" class="login-layout">
      <form class="login-panel" @submit.prevent="handleLogin">
        <span class="section-kicker">WORKSPACE KNOWLEDGE</span>
        <h2>员工登录</h2>
        <p>登录后访问工作室内部知识库</p>
        <label class="field-label" for="login-username">用户名</label>
        <input
          id="login-username"
          v-model="loginUsername"
          class="text-input"
          autocomplete="username"
          maxlength="64"
          required
        />
        <label class="field-label" for="login-password">密码</label>
        <input
          id="login-password"
          v-model="loginPassword"
          class="text-input"
          type="password"
          autocomplete="current-password"
          minlength="8"
          maxlength="128"
          required
        />
        <button class="primary-button full-width" type="submit" :disabled="isLoggingIn">
          <span v-if="isLoggingIn" class="button-spinner"></span>
          {{ isLoggingIn ? '正在登录…' : '登录' }}
        </button>
      </form>
    </main>

    <main v-else-if="!isAdmin || adminView === 'chat'" class="chat-layout">
      <section class="chat-panel">
        <div class="chat-heading">
          <div>
            <span class="section-kicker">AI KNOWLEDGE ASSISTANT</span>
            <h2>员工制度问答</h2>
            <p v-if="!isAdmin">{{ currentUser.department_name || '所属部门未知' }} · 回答仅基于本部门已导入的知识库资料</p>
            <p v-else>回答仅基于已导入的企业知识库资料</p>
          </div>
          <button class="clear-button" @click="clearConversation">清空对话</button>
        </div>

        <div class="message-list" aria-live="polite">
          <div v-for="(message, index) in messages" :key="`${index}-${message.role}`" class="message-row" :class="message.role">
            <div class="avatar">{{ message.role === 'assistant' ? '知' : '我' }}</div>
            <div class="message-content">
              <span class="message-label">{{ message.role === 'assistant' ? '知识库助手' : '我' }}</span>
              <div class="message-bubble">{{ message.content }}</div>
              <div v-if="message.sources?.length" class="source-list">
                <span class="source-label">参考文档</span>
                <span v-for="source in message.sources" :key="source" class="source-tag">{{ source }}</span>
              </div>
            </div>
          </div>
          <div v-if="isSending" class="message-row assistant">
            <div class="avatar">知</div>
            <div class="message-content">
              <span class="message-label">知识库助手</span>
              <div v-if="streamingAnswer" class="message-bubble">{{ streamingAnswer }}</div>
              <div v-else class="message-bubble loading-bubble"><span></span><span></span><span></span> 正在检索并生成回答</div>
            </div>
          </div>
        </div>

        <div class="composer">
          <textarea v-model="question" rows="3" placeholder="例如：新员工请假需要走什么流程？" @keydown="handleQuestionKeydown"></textarea>
          <div class="composer-footer">
            <span>Enter 发送 · Shift + Enter 换行</span>
            <button class="send-button" :disabled="!canSend" @click="sendQuestion">
              {{ isSending ? '生成中…' : '发送问题' }}
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>
      </section>
    </main>

    <main v-else class="management-page">
      <div class="management-heading">
        <div>
          <span class="section-kicker">ADMINISTRATION</span>
          <h2>管理中心</h2>
          <p>管理工作室部门、员工账号和知识库文档</p>
        </div>
        <div class="management-summary">
          <span>{{ departments.length }} 个部门</span>
          <span>{{ employees.length }} 名员工</span>
          <span>{{ documents.length }} 份文档</span>
        </div>
      </div>

      <nav class="management-tabs" aria-label="管理类别">
        <button :class="{ active: managementTab === 'departments' }" @click="managementTab = 'departments'">部门</button>
        <button :class="{ active: managementTab === 'employees' }" @click="managementTab = 'employees'">员工</button>
        <button :class="{ active: managementTab === 'documents' }" @click="managementTab = 'documents'">知识库文档</button>
        <button class="refresh-management" title="刷新管理数据" aria-label="刷新管理数据" @click="refreshManagementData">↻</button>
      </nav>

      <section v-if="managementTab === 'departments'" class="management-content">
        <form class="create-row department-create" @submit.prevent="handleCreateDepartment">
          <div><strong>新增部门</strong><span>新部门将拥有独立的文档检索范围</span></div>
          <input v-model="newDepartmentName" class="text-input" maxlength="64" placeholder="输入部门名称" required />
          <button class="primary-button" type="submit" :disabled="isCreatingDepartment">{{ isCreatingDepartment ? '创建中…' : '创建部门' }}</button>
        </form>
        <div class="table-wrap">
          <table class="management-table">
            <thead><tr><th>部门名称</th><th>部门 ID</th><th>保护规则</th><th class="actions-cell">操作</th></tr></thead>
            <tbody>
              <tr v-for="department in departments" :key="department.id">
                <td>
                  <input v-if="editingDepartmentId === department.id" v-model="editingDepartmentName" class="table-input" maxlength="64" />
                  <strong v-else>{{ department.name }}</strong>
                </td>
                <td><code>{{ department.id }}</code></td>
                <td><span v-if="department.id === 'default'" class="subtle-label">默认部门，不可删除</span><span v-else class="subtle-label">有员工或文档时不可删除</span></td>
                <td class="actions-cell">
                  <template v-if="editingDepartmentId === department.id">
                    <button class="table-action primary-action" @click="saveDepartment(department)">保存</button>
                    <button class="table-action" @click="editingDepartmentId = null">取消</button>
                  </template>
                  <template v-else>
                    <button class="table-action" @click="beginEditDepartment(department)">编辑</button>
                    <button class="table-action danger-action" :disabled="department.id === 'default'" @click="handleDeleteDepartment(department)">删除</button>
                  </template>
                </td>
              </tr>
              <tr v-if="departments.length === 0"><td colspan="4" class="empty-row">暂无部门</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-else-if="managementTab === 'employees'" class="management-content">
        <form class="create-row employee-create" @submit.prevent="handleCreateEmployee">
          <div><strong>新增员工账号</strong><span>初始密码至少 8 位</span></div>
          <input v-model="newEmployeeUsername" class="text-input" autocomplete="off" maxlength="64" placeholder="用户名" required />
          <input v-model="newEmployeePassword" class="text-input" type="password" autocomplete="new-password" minlength="8" maxlength="128" placeholder="初始密码" required />
          <select v-model="employeeDepartmentId" class="text-input" required>
            <option v-for="department in departments" :key="department.id" :value="department.id">{{ department.name }}</option>
          </select>
          <button class="primary-button" type="submit" :disabled="isCreatingEmployee">{{ isCreatingEmployee ? '创建中…' : '创建账号' }}</button>
        </form>
        <div class="table-wrap">
          <table class="management-table employee-table">
            <thead><tr><th>用户名</th><th>所属部门</th><th>员工 ID / 重置密码</th><th class="actions-cell">操作</th></tr></thead>
            <tbody>
              <tr v-for="employee in employees" :key="employee.id">
                <td>
                  <input v-if="editingEmployeeId === employee.id" v-model="editingEmployeeUsername" class="table-input" maxlength="64" />
                  <strong v-else>{{ employee.username }}</strong>
                </td>
                <td>
                  <select v-if="editingEmployeeId === employee.id" v-model="editingEmployeeDepartmentId" class="table-input">
                    <option v-for="department in departments" :key="department.id" :value="department.id">{{ department.name }}</option>
                  </select>
                  <span v-else>{{ employee.department_name || departmentLabel(employee.department_id || undefined) }}</span>
                </td>
                <td>
                  <input v-if="editingEmployeeId === employee.id" v-model="editingEmployeePassword" class="table-input" type="password" minlength="8" maxlength="128" placeholder="留空不修改" />
                  <span v-else class="subtle-label">{{ employee.id }}</span>
                </td>
                <td class="actions-cell">
                  <template v-if="editingEmployeeId === employee.id">
                    <button class="table-action primary-action" @click="saveEmployee(employee)">保存</button>
                    <button class="table-action" @click="editingEmployeeId = null">取消</button>
                  </template>
                  <template v-else>
                    <button class="table-action" @click="beginEditEmployee(employee)">编辑</button>
                    <button class="table-action danger-action" @click="handleDeleteEmployee(employee)">删除</button>
                  </template>
                </td>
              </tr>
              <tr v-if="employees.length === 0"><td colspan="4" class="empty-row">暂无员工账号</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-else class="management-content">
        <form class="create-row document-create" @submit.prevent="handleUpload">
          <label class="file-picker" :class="{ selected: selectedFile }">
            <input type="file" accept="application/pdf,.pdf" @change="handleFileChange" />
            <span>{{ selectedFile ? selectedFile.name : '选择 PDF' }}</span>
          </label>
          <input v-model="documentId" class="text-input" maxlength="128" placeholder="文档 ID" required />
          <select v-model="uploadDepartmentId" class="text-input" required>
            <option v-for="department in departments" :key="department.id" :value="department.id">{{ department.name }}</option>
          </select>
          <button class="primary-button" type="submit" :disabled="!canUpload">{{ isUploading ? '导入中…' : '导入 PDF' }}</button>
        </form>
        <div class="table-wrap">
          <table class="management-table document-table">
            <thead><tr><th>文档 ID</th><th>所属部门</th><th>文本块</th><th>状态</th><th>更新时间</th><th class="actions-cell">操作</th></tr></thead>
            <tbody>
              <tr v-for="document in documents" :key="document.doc_id">
                <td><strong>{{ document.doc_id }}</strong></td>
                <td>{{ departmentLabel(document.department_id) }}</td>
                <td>{{ document.total_chunks || 0 }}</td>
                <td><span class="status-label">{{ document.status }}</span></td>
                <td>{{ formatDate(document.updated_at) }}</td>
                <td class="actions-cell"><button class="table-action danger-action" @click="handleDelete(document)">删除</button></td>
              </tr>
              <tr v-if="documents.length === 0"><td colspan="6" class="empty-row">还没有导入文档</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>

    <div v-if="notice" class="notice" :class="`notice-${notice.type}`">{{ notice.text }}</div>
  </div>
</template>
