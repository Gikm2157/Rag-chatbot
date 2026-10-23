export interface KnowledgeDocument {
  doc_id: string
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

export interface AuthUser {
  id: string
  username: string
  role: 'admin' | 'employee'
  department_id?: string | null
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

export function createEmployee(username: string, password: string): Promise<AuthUser> {
  return request<AuthUser>(`${API_BASE_URL}/auth/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function chat(question: string): Promise<ChatResponse> {
  return request<ChatResponse>(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: question }),
  })
}

export function listDocuments(): Promise<DocumentListResponse> {
  return request<DocumentListResponse>(`${API_BASE_URL}/ingest/docs?limit=50&offset=0`)
}

export function uploadDocument(fileName: string, file: File): Promise<IngestResponse> {
  const formData = new FormData()
  formData.append('file_name', fileName)
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
