<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  API_BASE_URL,
  chat,
  checkHealth,
  deleteDocument,
  listDocuments,
  uploadDocument,
  type KnowledgeDocument,
} from './api'

type Message = {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
}

const messages = ref<Message[]>([
  {
    role: 'assistant',
    content: '你好，我是企业知识库客服。你可以询问员工制度、工作流程和新员工入职相关内容。',
  },
])
const question = ref('')
const userId = ref('')
const isSending = ref(false)
const isUploading = ref(false)
const documents = ref<KnowledgeDocument[]>([])
const selectedFile = ref<File | null>(null)
const documentId = ref('')
const notice = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const health = ref<'checking' | 'ok' | 'error'>('checking')
const healthText = ref('检查中')
let healthTimer: number | undefined

const canSend = computed(() => question.value.trim().length > 0 && !isSending.value)
const canUpload = computed(() => Boolean(selectedFile.value && documentId.value.trim() && !isUploading.value))

function createUserId(): string {
  const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10)
  return `visitor-${suffix}`
}

function setNotice(type: 'success' | 'error', text: string) {
  notice.value = { type, text }
  window.setTimeout(() => {
    if (notice.value?.text === text) notice.value = null
  }, 4500)
}

async function refreshDocuments() {
  try {
    const result = await listDocuments()
    documents.value = result.docs
  } catch (error) {
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
    const response = await chat(content, userId.value)
    messages.value.push({
      role: 'assistant',
      content: response.data,
      sources: response.sources,
    })
  } catch (error) {
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
    setNotice('error', error instanceof Error ? error.message : '文档导入失败')
  } finally {
    isUploading.value = false
  }
}

async function handleDelete(document: KnowledgeDocument) {
  if (!window.confirm(`确定删除“${document.doc_id}”吗？删除后将无法检索这份文档。`)) return
  try {
    await deleteDocument(document.doc_id)
    setNotice('success', `已删除文档：${document.doc_id}`)
    await refreshDocuments()
  } catch (error) {
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

onMounted(() => {
  userId.value = localStorage.getItem('rag-chat-user-id') || createUserId()
  localStorage.setItem('rag-chat-user-id', userId.value)
  void refreshDocuments()
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
        <span class="health-pill" :class="`health-${health}`">
          <span class="health-dot"></span>{{ healthText }}
        </span>
      </div>
    </header>

    <main class="workspace">
      <aside class="sidebar">
        <section class="side-section intro-card">
          <span class="section-kicker">内部助手</span>
          <h2>让制度查找更简单</h2>
          <p>上传员工手册和企业制度，新员工可以直接通过对话了解工作规则。</p>
        </section>

        <section class="side-section">
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
              <button class="delete-button" :aria-label="`删除 ${document.doc_id}`" @click="handleDelete(document)">×</button>
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
