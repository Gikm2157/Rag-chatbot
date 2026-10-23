<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  API_BASE_URL,
  ApiError,
  chat,
  checkHealth,
  createEmployee,
  deleteDocument,
  getCurrentUser,
  login,
  logout,
  listDocuments,
  uploadDocument,
  type AuthUser,
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
const isSending = ref(false)
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

function setNotice(type: 'success' | 'error', text: string) {
  notice.value = { type, text }
  window.setTimeout(() => {
    if (notice.value?.text === text) notice.value = null
  }, 4500)
}

function clearSession() {
  currentUser.value = null
  documents.value = []
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

  try {
    const response = await chat(content)
    messages.value.push({
      role: 'assistant',
      content: response.data,
      sources: response.sources,
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
    const result = await uploadDocument(documentId.value.trim(), selectedFile.value)
    const data = result.data
    setNotice('success', `文档${data.status === 'skipped' ? '无需更新' : '导入完成'}：${data.doc_id}`)
    selectedFile.value = null
    documentId.value = ''
    await refreshDocuments()
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
    await refreshDocuments()
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
    await refreshDocuments()
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
    const user = await createEmployee(username, newEmployeePassword.value)
    newEmployeeUsername.value = ''
    newEmployeePassword.value = ''
    setNotice('success', `员工账号 ${user.username} 已创建`)
  } catch (error) {
    if (handleUnauthorized(error)) return
    setNotice('error', error instanceof Error ? error.message : '创建员工账号失败')
  } finally {
    isCreatingEmployee.value = false
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
    messages.value = [{ role: 'assistant', content: welcomeMessage }]
  }
}

async function restoreSession() {
  isCheckingAuth.value = true
  try {
    currentUser.value = await getCurrentUser()
    await refreshDocuments()
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
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-block">
        <div class="brand-mark">知</div>
        <div>
          <p class="eyebrow">WORKSPACE KNOWLEDGE</p>
          <h1>企业知识库客服</h1>
        </div>
      </div>
      <div class="topbar-meta">
        <span class="api-address">API · {{ API_BASE_URL }}</span>
        <span v-if="currentUser" class="user-pill">
          {{ currentUser.username }} · {{ isAdmin ? '管理员' : '员工' }}
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

    <main v-else class="workspace">
      <aside class="sidebar">
        <section class="side-section intro-card">
          <span class="section-kicker">内部助手</span>
          <h2>让制度查找更简单</h2>
          <p>上传员工手册和企业制度，新员工可以直接通过对话了解工作规则。</p>
        </section>

        <section v-if="isAdmin" class="side-section">
          <div class="section-heading">
            <div>
              <span class="section-kicker">知识库管理</span>
              <h3>导入文档</h3>
            </div>
            <span class="doc-count">{{ documents.length }} 份</span>
          </div>
          <label class="file-dropzone" :class="{ selected: selectedFile }">
            <input type="file" accept="application/pdf,.pdf" @change="handleFileChange" />
            <span class="upload-icon">↑</span>
            <strong>{{ selectedFile ? selectedFile.name : '选择 PDF 文件' }}</strong>
            <small>{{ selectedFile ? '已选择，准备导入' : '最大支持 50 MB' }}</small>
          </label>
          <label class="field-label" for="document-id">文档 ID</label>
          <input id="document-id" v-model="documentId" class="text-input" maxlength="128" placeholder="例如：员工手册" />
          <button class="primary-button full-width" :disabled="!canUpload" @click="handleUpload">
            <span v-if="isUploading" class="button-spinner"></span>
            {{ isUploading ? '正在导入…' : '导入知识库' }}
          </button>
        </section>

        <section v-if="isAdmin" class="side-section">
          <div class="section-heading">
            <div>
              <span class="section-kicker">账号管理</span>
              <h3>创建员工账号</h3>
            </div>
          </div>
          <form class="admin-form" @submit.prevent="handleCreateEmployee">
            <label class="field-label" for="new-employee-username">用户名</label>
            <input
              id="new-employee-username"
              v-model="newEmployeeUsername"
              class="text-input"
              autocomplete="off"
              maxlength="64"
              required
            />
            <label class="field-label" for="new-employee-password">初始密码</label>
            <input
              id="new-employee-password"
              v-model="newEmployeePassword"
              class="text-input"
              type="password"
              autocomplete="new-password"
              minlength="8"
              maxlength="128"
              required
            />
            <button class="secondary-button full-width" type="submit" :disabled="isCreatingEmployee">
              {{ isCreatingEmployee ? '正在创建…' : '创建员工账号' }}
            </button>
          </form>
        </section>

        <section class="side-section document-section">
          <div class="section-heading">
            <div>
              <span class="section-kicker">已导入内容</span>
              <h3>文档列表</h3>
            </div>
            <button class="text-button" @click="refreshDocuments">刷新</button>
          </div>
          <div v-if="documents.length" class="document-list">
            <article v-for="document in documents" :key="document.doc_id" class="document-item">
              <div class="document-icon">PDF</div>
              <div class="document-info">
                <strong :title="document.doc_id">{{ document.doc_id }}</strong>
                <span>{{ document.total_chunks || 0 }} 个文本块 · {{ formatDate(document.updated_at) }}</span>
              </div>
              <button v-if="isAdmin" class="delete-button" :aria-label="`删除 ${document.doc_id}`" @click="handleDelete(document)">×</button>
            </article>
          </div>
          <div v-else class="empty-documents">
            <span>⌁</span>
            <p>还没有导入文档</p>
            <small>上传一份 PDF 开始构建知识库</small>
          </div>
        </section>
      </aside>

      <section class="chat-panel">
        <div class="chat-heading">
          <div>
            <span class="section-kicker">AI KNOWLEDGE ASSISTANT</span>
            <h2>员工制度问答</h2>
            <p>回答仅基于已导入的企业知识库资料</p>
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
              <div class="message-bubble loading-bubble"><span></span><span></span><span></span> 正在检索并生成回答</div>
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

    <div v-if="notice" class="notice" :class="`notice-${notice.type}`">{{ notice.text }}</div>
  </div>
</template>
