export interface KnowledgeDocument {
  doc_id: string
  department_id?: string
  status: string
  file_name?: string
  file_hash?: string
  version?: string
  total_chunks?: string
  error?: string
  updated_at?: string
}

interface DocumentListResponse {
  total: number
  docs: KnowledgeDocument[]
}

interface IngestResponse {
  status: string
  data: {
    doc_id: string
    status: string
    added?: number
    removed?: number
    total?: number
    reason?: string
  }
}

export interface ChatResponse {
  status: string
  data: string
  sources: string[]
}

export interface ChatStreamHandlers {
  onToken: (content: string) => void
  onSources: (sources: string[]) => void
}

export interface AuthUser {
  id: string
  username: string
  role: 'admin' | 'employee'
  department_id?: string | null
  department_name?: string | null
}

export interface Department {
  id: string
  name: string
}

interface AuthResponse {
  status: string
  user: AuthUser
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// 默认使用浏览器当前访问的主机名，避免前端用局域网 IP、API 却用 localhost
// 导致 Cookie 被浏览器视为跨站请求而不发送。部署到其他主机时仍可用环境变量覆盖。
const browserApiBaseUrl = typeof window === 'undefined'
  ? 'http://localhost:8000/api/v1'
  : `${window.location.protocol}//${window.location.hostname}:8000/api/v1`
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || browserApiBaseUrl).replace(/\/$/, '')
const API_ORIGIN = API_BASE_URL.replace(/\/api\/v1$/, '')

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { ...init, credentials: 'include' })
  } catch {
    throw new Error('无法连接后端服务，请确认 FastAPI 已启动。')
  }

  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }

  if (!response.ok) {
    const record = body as { detail?: string; error?: string } | null
    throw new ApiError(record?.detail || record?.error || `请求失败（HTTP ${response.status}）`, response.status)
  }

  return body as T
}

export function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>(`${API_ORIGIN}/health`)
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function getCurrentUser(): Promise<AuthUser> {
  return request<AuthUser>(`${API_BASE_URL}/auth/me`)
}

export function logout(): Promise<{ status: string }> {
  return request<{ status: string }>(`${API_BASE_URL}/auth/logout`, { method: 'POST' })
}

export function listDepartments(): Promise<Department[]> {
  return request<Department[]>(`${API_BASE_URL}/auth/departments`)
}

export function createDepartment(name: string): Promise<Department> {
  return request<Department>(`${API_BASE_URL}/auth/departments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function updateDepartment(departmentId: string, name: string): Promise<Department> {
  return request<Department>(`${API_BASE_URL}/auth/departments/${encodeURIComponent(departmentId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function deleteDepartment(departmentId: string): Promise<{ status: string; department_id: string }> {
  return request<{ status: string; department_id: string }>(`${API_BASE_URL}/auth/departments/${encodeURIComponent(departmentId)}`, {
    method: 'DELETE',
  })
}

export function createEmployee(username: string, password: string, departmentId: string): Promise<AuthUser> {
  return request<AuthUser>(`${API_BASE_URL}/auth/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, department_id: departmentId }),
  })
}

export function listEmployees(): Promise<AuthUser[]> {
  return request<AuthUser[]>(`${API_BASE_URL}/auth/users`)
}

export function updateEmployee(
  userId: string,
  username: string,
  departmentId: string,
  password?: string,
): Promise<AuthUser> {
  return request<AuthUser>(`${API_BASE_URL}/auth/users/${encodeURIComponent(userId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, department_id: departmentId, ...(password ? { password } : {}) }),
  })
}

export function deleteEmployee(userId: string): Promise<{ status: string; user_id: string }> {
  return request<{ status: string; user_id: string }>(`${API_BASE_URL}/auth/users/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  })
}

export function chat(question: string): Promise<ChatResponse> {
  return request<ChatResponse>(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: question }),
  })
}

export async function streamChat(question: string, handlers: ChatStreamHandlers): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ q: question }),
      credentials: 'include',
    })
  } catch {
    throw new Error('无法连接后端服务，请确认 FastAPI 已启动。')
  }

  if (!response.ok) {
    const text = await response.text()
    let body: unknown = null
    try {
      body = text ? JSON.parse(text) : null
    } catch {
      body = text
    }
    const record = body as { detail?: string; error?: string } | null
    throw new ApiError(record?.detail || record?.error || `请求失败（HTTP ${response.status}）`, response.status)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应。')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false

  const handleEvent = (rawEvent: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of rawEvent.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) return
    const payload = JSON.parse(dataLines.join('\n')) as {
      content?: string
      sources?: string[]
      message?: string
      status?: string
    }
    if (event === 'token' && payload.content) handlers.onToken(payload.content)
    if (event === 'sources') handlers.onSources(payload.sources || [])
    if (event === 'done') completed = true
    if (event === 'error') throw new Error(payload.message || '生成回答失败')
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() || ''
      for (const event of events) handleEvent(event)
      if (done) break
    }
    if (buffer.trim()) handleEvent(buffer)
    if (!completed) throw new Error('流式连接提前结束，请重试。')
  } catch (error) {
    await reader.cancel().catch(() => undefined)
    throw error
  } finally {
    reader.releaseLock()
  }
}

export function listDocuments(): Promise<DocumentListResponse> {
  return request<DocumentListResponse>(`${API_BASE_URL}/ingest/docs?limit=50&offset=0`)
}

export function uploadDocument(fileName: string, file: File, departmentId: string): Promise<IngestResponse> {
  const formData = new FormData()
  formData.append('file_name', fileName)
  formData.append('department_id', departmentId)
  formData.append('file', file)
  return request<IngestResponse>(`${API_BASE_URL}/ingest/upload`, {
    method: 'POST',
    body: formData,
  })
}

export function deleteDocument(docId: string): Promise<{ status: string; doc_id: string }> {
  return request<{ status: string; doc_id: string }>(`${API_BASE_URL}/ingest/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
  })
}

export { API_BASE_URL }
