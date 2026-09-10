export type BatchStatus = 'CREATED' | 'QUEUED' | 'RUNNING' | 'PAUSED' | 'STOPPING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export type Batch = {
  id: string
  referral: string
  target: number
  successful: number
  failed: number
  skipped: number
  attempted: number
  retries: number
  remaining: number
  progress_percent: number
  started_at?: string | null
  completed_at?: string | null
  estimated_remaining: number
  status: BatchStatus
  created_at: string
  error_message?: string | null
}

export type Readiness = {
  status: string
  database: string
  worker: string
}

export type WorkerInfo = {
  active_worker_id: string
  queue_size: number
  recent_jobs: Array<{
    id: string
    batch_id: string
    status: string
    worker_id: string | null
    started_at: string | null
    heartbeat_at: string | null
  }>
  timestamp: string
}

const rawApiUrl = (import.meta.env.VITE_API_URL ?? import.meta.env.VITE_APP_URL ?? 'http://127.0.0.1:8000').trim()
export const API_URL = rawApiUrl.replace(/\/+$/, '')

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json() as Promise<T>
}

export function listBatches(limit = 20, status?: string) {
  const query = status ? `?limit=${limit}&status=${status}` : `?limit=${limit}`
  return request<Batch[]>(`/batches${query}`)
}

export function createBatch(referral: string, autoStart = true) {
  return request<Batch>(`/batches?auto_start=${autoStart}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ referral, auto_start: autoStart }),
  })
}

export function getBatch(id: string) {
  return request<Batch>(`/batches/${id}`)
}

export function updateBatch(id: string, action: 'start' | 'pause' | 'resume' | 'stop') {
  return request<Batch>(`/batches/${id}/${action}`, { method: 'POST' })
}

export function getHealth() {
  return request<{ status: string; database: string }>('/health')
}

export function getReadiness() {
  return request<Readiness>('/ready')
}

export function getWorkers() {
  return request<WorkerInfo>('/workers')
}

export function getExportUrl(id: string, format: 'csv' | 'json'): string {
  return `${API_URL}/batches/${id}/export/${format}`
}
