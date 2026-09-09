import { useEffect, useState } from 'react'
import {
  createBatch,
  getBatch,
  getHealth,
  getReadiness,
  getWorkers,
  updateBatch,
  getExportUrl,
  type Batch,
  type Readiness,
  type WorkerInfo,
} from './services/api'
import './App.css'

type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected'
type ActiveTab = 'dashboard' | 'admin'

function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard')
  const [referral, setReferral] = useState('')
  const [batch, setBatch] = useState<Batch | null>(null)
  const [loading, setLoading] = useState(false)
  const [operation, setOperation] = useState<'start' | 'pause' | 'resume' | 'stop' | null>(null)
  const [error, setError] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected')

  // Admin Data
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [workerInfo, setWorkerInfo] = useState<WorkerInfo | null>(null)
  const [healthStatus, setHealthStatus] = useState<string>('checking...')

  // Fetch admin stats when admin tab is opened or periodically
  useEffect(() => {
    async function fetchAdminData() {
      try {
        const [r, w, h] = await Promise.all([
          getReadiness().catch(() => null),
          getWorkers().catch(() => null),
          getHealth().catch(() => ({ status: 'error', database: 'error' })),
        ])
        if (r) setReadiness(r)
        if (w) setWorkerInfo(w)
        if (h) setHealthStatus(h.status)
      } catch {
        setHealthStatus('error')
      }
    }
    fetchAdminData()
    const interval = setInterval(fetchAdminData, 5000)
    return () => clearInterval(interval)
  }, [])

  // SSE & Live Status Updates
  useEffect(() => {
    const batchId = batch?.id
    if (!batchId) {
      setConnectionStatus('disconnected')
      return
    }

    let reconnectTimeout: number | null = null
    let isActive = true
    const apiUrl = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

    function connectToEvents() {
      if (!isActive) return

      // Refetch latest batch state immediately on reconnect/connect
      getBatch(batchId)
        .then((b) => { if (isActive) setBatch(b) })
        .catch(() => {})

      const events = new EventSource(`${apiUrl}/batches/${batchId}/events`)

      events.onopen = () => {
        if (isActive) {
          setConnectionStatus('connected')
        }
      }

      events.onmessage = (event) => {
        try {
          const nextBatch = JSON.parse(event.data) as Batch
          setBatch(nextBatch)
          if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(nextBatch.status)) {
            events.close()
            setConnectionStatus('disconnected')
          }
        } catch {
          // ignore parsing error keepalive
        }
      }

      events.onerror = () => {
        if (!isActive) return

        events.close()
        setConnectionStatus('reconnecting')

        reconnectTimeout = window.setTimeout(() => {
          if (isActive) {
            connectToEvents()
          }
        }, 3000)
      }

      return events
    }

    const events = connectToEvents()

    return () => {
      isActive = false
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (events) events.close()
    }
  }, [batch?.id])

  async function handleCreateBatch() {
    if (!referral.trim()) {
      setError('Please enter a referral code first.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const created = await createBatch(referral.trim())
      setBatch(created)
    } catch {
      setError('Could not connect to the backend server.')
    } finally {
      setLoading(false)
    }
  }

  async function handleControl(action: 'start' | 'pause' | 'resume' | 'stop') {
    if (!batch || operation) return
    setError('')
    setOperation(action)
    try {
      const updated = await updateBatch(batch.id, action)
      setBatch(updated)
    } catch {
      setError(`Action '${action}' is not available in state '${batch.status}'.`)
    } finally {
      setOperation(null)
    }
  }

  const progress = batch ? Math.min(100, Math.max(0, batch.progress_percent ?? 0)) : 0
  const isRunning = batch?.status === 'RUNNING' || batch?.status === 'QUEUED' || batch?.status === 'PAUSED'

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="brand">
          <div className="brand-icon">SA</div>
          <span>Signup Automation</span>
        </div>

        <div className="header-meta">
          <nav className="nav-tabs">
            <button
              className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}
            >
              Batch Operations
            </button>
            <button
              className={`tab-btn ${activeTab === 'admin' ? 'active' : ''}`}
              onClick={() => setActiveTab('admin')}
            >
              System & Workers
            </button>
          </nav>

          {batch && (
            <div className="connection-badge">
              <span className={`connection-dot ${connectionStatus}`} />
              <span>
                {connectionStatus === 'connected'
                  ? 'Live Stream'
                  : connectionStatus === 'reconnecting'
                  ? 'Reconnecting...'
                  : 'Disconnected'}
              </span>
            </div>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      {activeTab === 'dashboard' ? (
        <>
          <section className="hero">
            <p className="eyebrow">CONTROL PANEL / BATCH OPERATIONS</p>
            <h1>Production Automation Hub</h1>
            <p>Launch referral batches, track real-time signup progress, and export results.</p>
          </section>

          <div className="dashboard-grid">
            {/* Create Batch Card */}
            <div className="card">
              <p className="card-label">01 / NEW BATCH</p>
              <div className="form-group">
                <label htmlFor="referral-input">Referral Code</label>
                <div className="input-row">
                  <input
                    id="referral-input"
                    className="input-field"
                    value={referral}
                    onChange={(e) => setReferral(e.target.value)}
                    placeholder="e.g. PROMO2026"
                    maxLength={120}
                  />
                </div>
              </div>
              <button
                type="button"
                className="btn-primary"
                style={{ width: '100%' }}
                onClick={handleCreateBatch}
                disabled={loading}
              >
                {loading ? 'Creating Batch...' : 'Create Batch'}
              </button>
              {error && <p className="error-msg">{error}</p>}
            </div>

            {/* Live Status Card */}
            <div className="card">
              <div className="status-header">
                <p className="card-label">02 / LIVE STATUS & METRICS</p>
                {batch && <span className={`status-badge ${batch.status}`}>{batch.status}</span>}
              </div>

              {batch ? (
                <>
                  <div style={{ marginBottom: '16px' }}>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>{batch.referral}</div>
                    <div style={{ fontSize: '0.8125rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      ID: {batch.id}
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div className="progress-container">
                    <div className="progress-track">
                      <div className="progress-bar" style={{ width: `${progress}%` }} />
                    </div>
                    <div className="progress-labels">
                      <span>{batch.successful} / {batch.target} Completed</span>
                      <span style={{ fontWeight: 700 }}>{progress}%</span>
                    </div>
                  </div>

                  {/* Metrics Breakdown */}
                  <div className="metrics-grid">
                    <div className="metric-box">
                      <div className="metric-val success">{batch.successful}</div>
                      <div className="metric-lbl">Success</div>
                    </div>
                    <div className="metric-box">
                      <div className="metric-val failed">{batch.failed}</div>
                      <div className="metric-lbl">Failed</div>
                    </div>
                    <div className="metric-box">
                      <div className="metric-val skipped">{batch.skipped ?? 0}</div>
                      <div className="metric-lbl">Skipped</div>
                    </div>
                    <div className="metric-box">
                      <div className="metric-val retries">{batch.retries ?? 0}</div>
                      <div className="metric-lbl">Retries</div>
                    </div>
                  </div>

                  {/* Batch Controls */}
                  <div className="actions-bar">
                    {batch.status === 'CREATED' && (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => handleControl('start')}
                        disabled={operation !== null}
                      >
                        {operation === 'start' ? 'Starting...' : 'Start Batch'}
                      </button>
                    )}
                    {batch.status === 'RUNNING' && (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => handleControl('pause')}
                        disabled={operation !== null}
                      >
                        {operation === 'pause' ? 'Pausing...' : 'Pause'}
                      </button>
                    )}
                    {batch.status === 'PAUSED' && (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => handleControl('resume')}
                        disabled={operation !== null}
                      >
                        {operation === 'resume' ? 'Resuming...' : 'Resume'}
                      </button>
                    )}
                    {isRunning && (
                      <button
                        type="button"
                        className="btn-danger"
                        onClick={() => handleControl('stop')}
                        disabled={operation !== null}
                      >
                        {operation === 'stop' ? 'Stopping...' : 'Stop'}
                      </button>
                    )}
                  </div>

                  {/* Export Options */}
                  <div className="exports-section">
                    <span className="exports-label">Export Batch Data:</span>
                    <div className="export-btns">
                      <a
                        href={getExportUrl(batch.id, 'csv')}
                        download
                        className="btn-secondary"
                        style={{ textDecoration: 'none', display: 'inline-block' }}
                      >
                        Download CSV
                      </a>
                      <a
                        href={getExportUrl(batch.id, 'json')}
                        download
                        className="btn-secondary"
                        style={{ textDecoration: 'none', display: 'inline-block' }}
                      >
                        Download JSON
                      </a>
                    </div>
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <p>No active batch selected. Create a batch to start monitoring.</p>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        /* Admin & Worker View */
        <div className="admin-grid">
          {/* System Health */}
          <div className="admin-card">
            <p className="card-label">SYSTEM HEALTH & READINESS</p>
            <table className="admin-table">
              <tbody>
                <tr>
                  <td>API Status</td>
                  <td>
                    <span className="status-badge COMPLETED">{healthStatus.toUpperCase()}</span>
                  </td>
                </tr>
                <tr>
                  <td>Database</td>
                  <td>
                    <span className={`status-badge ${readiness?.database === 'ok' ? 'COMPLETED' : 'FAILED'}`}>
                      {readiness?.database ?? 'CHECKING'}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td>Worker System</td>
                  <td>
                    <span className="status-badge QUEUED">{readiness?.worker ?? 'UNKNOWN'}</span>
                  </td>
                </tr>
                <tr>
                  <td>Active Worker ID</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{workerInfo?.active_worker_id ?? 'N/A'}</td>
                </tr>
                <tr>
                  <td>Job Queue Size</td>
                  <td style={{ fontWeight: 700 }}>{workerInfo?.queue_size ?? 0} jobs</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Recent Jobs */}
          <div className="admin-card">
            <p className="card-label">RECENT WORKER JOBS</p>
            {workerInfo?.recent_jobs && workerInfo.recent_jobs.length > 0 ? (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Batch ID</th>
                    <th>Status</th>
                    <th>Worker</th>
                  </tr>
                </thead>
                <tbody>
                  {workerInfo.recent_jobs.slice(0, 6).map((j) => (
                    <tr key={j.id}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{j.id.slice(0, 8)}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{j.batch_id.slice(0, 8)}</td>
                      <td>
                        <span className={`status-badge ${j.status}`}>{j.status}</span>
                      </td>
                      <td>{j.worker_id ?? 'Unassigned'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <p>No recent worker jobs recorded.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <footer>
        <span>Production Automation Engine</span>
        <span>PostgreSQL / SQLite · Real-time SSE · Decoupled Workers</span>
      </footer>
    </div>
  )
}

export default App
