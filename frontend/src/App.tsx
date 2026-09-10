import { useEffect, useState } from 'react'
import {
  createBatch,
  getBatch,
  getHealth,
  getReadiness,
  getWorkers,
  updateBatch,
  listBatches,
  API_URL,
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
  const [batchesList, setBatchesList] = useState<Batch[]>([])
  const [autoStart, setAutoStart] = useState(true)
  const [loading, setLoading] = useState(false)
  const [operation, setOperation] = useState<'start' | 'pause' | 'resume' | 'stop' | null>(null)
  const [error, setError] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected')

  // Admin Data
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [workerInfo, setWorkerInfo] = useState<WorkerInfo | null>(null)
  const [healthStatus, setHealthStatus] = useState<string>('checking...')

  // Fetch admin stats & batches list periodically
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

    async function fetchBatches() {
      try {
        const list = await listBatches(30)
        if (list && Array.isArray(list)) {
          setBatchesList(list)
          setBatch((prev) => {
            if (!prev && list.length > 0) {
              const active = list.find((b) => b.status === 'RUNNING' || b.status === 'QUEUED') || list[0]
              return active
            }
            if (prev) {
              const updated = list.find((b) => b.id === prev.id)
              return updated || prev
            }
            return prev
          })
        }
      } catch {
        // ignore
      }
    }

    fetchAdminData()
    fetchBatches()
    const interval = setInterval(fetchAdminData, 5000)
    const bInterval = setInterval(fetchBatches, 3000)
    return () => {
      clearInterval(interval)
      clearInterval(bInterval)
    }
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

    function connectToEvents() {
      if (!isActive) return

      // Refetch latest batch state immediately on reconnect/connect
      getBatch(batchId!)
        .then((b) => { if (isActive) setBatch(b) })
        .catch(() => {})

      const events = new EventSource(`${API_URL}/batches/${batchId}/events`)

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
            isActive = false
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
        if (batch?.status && ['COMPLETED', 'FAILED', 'CANCELLED'].includes(batch.status)) {
          return
        }
        setConnectionStatus('reconnecting')
        reconnectTimeout = window.setTimeout(() => {
          if (isActive) {
            connectToEvents()
          }
        }, 4000)
      }

      return events
    }

    const events = connectToEvents()

    return () => {
      isActive = false
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (events) events.close()
    }
  }, [batch?.id, batch?.status])

  async function handleCreateBatch(count: number = 1) {
    const rawCodes = referral
      .split(/[\n,;\s]+/)
      .map((c) => c.trim())
      .filter(Boolean)

    if (rawCodes.length === 0) {
      setError('Please enter at least one referral code.')
      return
    }
    setError('')
    setLoading(true)
    try {
      let codesToRun: string[] = []
      if (rawCodes.length > 1) {
        // If user provided multiple referral codes, launch one task per code!
        codesToRun = rawCodes
      } else {
        // If user provided 1 code, run 'count' tasks with the exact same referral code
        codesToRun = Array(count).fill(rawCodes[0])
      }

      const promises = codesToRun.map((code) => createBatch(code, autoStart))
      const results = await Promise.all(promises)
      if (results.length > 0) setBatch(results[0])
      const list = await listBatches(30)
      setBatchesList(list)
    } catch {
      setError('Could not connect to the backend server.')
    } finally {
      setLoading(false)
    }
  }

  async function handleControl(action: 'start' | 'pause' | 'resume' | 'stop', targetBatchId?: string) {
    const id = targetBatchId || batch?.id
    if (!id || operation) return
    setError('')
    setOperation(action)
    try {
      const updated = await updateBatch(id, action)
      if (!targetBatchId || targetBatchId === batch?.id) {
        setBatch(updated)
      }
      const list = await listBatches(30)
      setBatchesList(list)
    } catch {
      setError(`Action '${action}' failed or is not available.`)
    } finally {
      setOperation(null)
    }
  }

  const progress = batch ? Math.min(100, Math.max(0, batch.progress_percent ?? 0)) : 0
  const isRunning = batch?.status === 'RUNNING' || batch?.status === 'QUEUED' || batch?.status === 'PAUSED'

  const runningBatchesCount = batchesList.filter((b) => b.status === 'RUNNING').length
  const queuedBatchesCount = batchesList.filter((b) => b.status === 'QUEUED').length
  const detectedCodes = referral.split(/[\n,;\s]+/).map((c) => c.trim()).filter(Boolean)

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
              <span
                className={`connection-dot ${
                  batch.status === 'RUNNING'
                    ? 'connected'
                    : batch.status === 'QUEUED'
                    ? 'reconnecting'
                    : batch.status === 'COMPLETED'
                    ? 'connected'
                    : 'disconnected'
                }`}
              />
              <span>
                {batch.status === 'RUNNING'
                  ? 'Live Stream'
                  : batch.status === 'QUEUED'
                  ? 'Queued'
                  : batch.status === 'COMPLETED'
                  ? 'Completed'
                  : batch.status === 'FAILED'
                  ? 'Finished / Stopped'
                  : connectionStatus === 'connected'
                  ? 'Connected'
                  : connectionStatus === 'reconnecting'
                  ? 'Reconnecting...'
                  : 'Idle'}
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
            <p>Launch referral batches, scale concurrent tasks (10+ simultaneous), and monitor live signups.</p>
          </section>

          <div className="dashboard-grid">
            {/* Create Batch Card */}
            <div className="card">
              <p className="card-label">01 / NEW BATCH</p>
              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <label htmlFor="referral-input" style={{ margin: 0 }}>Referral Code(s)</label>
                  {detectedCodes.length > 0 && (
                    <span style={{ fontSize: '0.75rem', color: detectedCodes.length >= 10 ? '#10b981' : '#38bdf8', fontWeight: 600 }}>
                      {detectedCodes.length} {detectedCodes.length === 1 ? 'referral' : 'referrals'} detected
                    </span>
                  )}
                </div>
                <div className="input-row">
                  <textarea
                    id="referral-input"
                    className="input-field"
                    rows={3}
                    value={referral}
                    onChange={(e) => setReferral(e.target.value)}
                    placeholder="Enter 1 referral code or paste 10 codes (separated by commas or lines)"
                    style={{ resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  id="auto-start-toggle"
                  checked={autoStart}
                  onChange={(e) => setAutoStart(e.target.checked)}
                  style={{ accentColor: 'var(--accent-blue)', width: '16px', height: '16px', cursor: 'pointer' }}
                />
                <label htmlFor="auto-start-toggle" style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', cursor: 'pointer', userSelect: 'none' }}>
                  Auto-start tasks immediately upon creation
                </label>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button
                  type="button"
                  className="btn-primary"
                  style={{ width: '100%' }}
                  onClick={() => handleCreateBatch(1)}
                  disabled={loading}
                >
                  {loading
                    ? 'Launching Tasks...'
                    : detectedCodes.length > 1
                    ? `Launch ${detectedCodes.length} Tasks (${detectedCodes.length} Referrals)`
                    : 'Launch 1 Task'}
                </button>

                {detectedCodes.length <= 1 && (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ width: '100%', borderColor: 'rgba(59, 130, 246, 0.4)', color: '#38bdf8' }}
                    onClick={() => handleCreateBatch(10)}
                    disabled={loading}
                  >
                    {loading ? 'Launching 10 Tasks...' : '⚡ Launch 10 Tasks (Same Referral)'}
                  </button>
                )}
              </div>

              {error && <p className="error-msg" style={{ marginTop: '12px' }}>{error}</p>}
            </div>

            {/* Live Status Card */}
            <div className="card">
              <div className="status-header">
                <p className="card-label">02 / LIVE FOCUS & METRICS</p>
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

                  {batch.status === 'FAILED' && (
                    <div
                      style={{
                        background: 'rgba(239, 68, 68, 0.12)',
                        border: '1px solid rgba(239, 68, 68, 0.4)',
                        padding: '12px 16px',
                        borderRadius: '12px',
                        marginBottom: '16px',
                        color: '#fca5a5',
                        fontSize: '0.875rem',
                      }}
                    >
                      <strong style={{ display: 'block', color: '#f87171', marginBottom: '4px' }}>
                        ⚠️ Referral Limit Reached or Rejected:
                      </strong>
                      {batch.error_message ||
                        'This referral code has reached its maximum limit on the target site or signups were rejected. Please use a fresh referral code.'}
                    </div>
                  )}

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
                </>
              ) : (
                <div className="empty-state">
                  <p>No active batch selected. Create a batch to start monitoring.</p>
                </div>
              )}
            </div>
          </div>

          {/* Concurrent Batches & Tasks Overview Table */}
          <div className="card" style={{ marginBottom: '32px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <p className="card-label" style={{ margin: 0 }}>ACTIVE & QUEUED TASKS ({batchesList.length})</p>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Running: <strong style={{ color: '#10b981' }}>{runningBatchesCount}</strong> · Queued: <strong style={{ color: '#38bdf8' }}>{queuedBatchesCount}</strong>
                </div>
              </div>
            </div>

            {batchesList.length > 0 ? (
              <div style={{ overflowX: 'auto', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
                <table className="admin-table" style={{ margin: 0 }}>
                  <thead>
                    <tr>
                      <th>Batch ID</th>
                      <th>Referral Code</th>
                      <th>Status</th>
                      <th>Progress</th>
                      <th>Success</th>
                      <th>Failed</th>
                      <th>Skipped</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchesList.map((b) => (
                      <tr
                        key={b.id}
                        style={{
                          background: batch?.id === b.id ? 'rgba(59, 130, 246, 0.08)' : 'transparent',
                          cursor: 'pointer',
                        }}
                        onClick={() => setBatch(b)}
                      >
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{b.id.slice(0, 8)}</td>
                        <td style={{ fontWeight: 600 }}>{b.referral}</td>
                        <td>
                          <span className={`status-badge ${b.status}`}>{b.status}</span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '120px' }}>
                            <div style={{ flex: 1, background: 'rgba(255,255,255,0.1)', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
                              <div
                                style={{
                                  width: `${Math.min(100, Math.max(0, b.progress_percent ?? 0))}%`,
                                  background: 'var(--accent-blue)',
                                  height: '100%',
                                }}
                              />
                            </div>
                            <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>{b.progress_percent ?? 0}%</span>
                          </div>
                        </td>
                        <td style={{ color: '#34d399', fontWeight: 600 }}>{b.successful}</td>
                        <td style={{ color: '#f87171' }}>{b.failed}</td>
                        <td style={{ color: '#fbbf24' }}>{b.skipped ?? 0}</td>
                        <td>
                          <div style={{ display: 'flex', gap: '6px' }} onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              className="btn-secondary"
                              style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                              onClick={() => setBatch(b)}
                            >
                              {batch?.id === b.id ? 'Monitoring' : 'Monitor'}
                            </button>
                            {b.status === 'RUNNING' && (
                              <button
                                type="button"
                                className="btn-danger"
                                style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                onClick={() => handleControl('stop', b.id)}
                              >
                                Stop
                              </button>
                            )}
                            {b.status === 'CREATED' && (
                              <button
                                type="button"
                                className="btn-primary"
                                style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                onClick={() => handleControl('start', b.id)}
                              >
                                Start
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <p>No batches found. Launch a batch above to get started.</p>
              </div>
            )}
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
                    <span className={`status-badge ${healthStatus === 'ok' || healthStatus === 'healthy' ? 'COMPLETED' : 'FAILED'}`}>
                      {healthStatus.toUpperCase()}
                    </span>
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
                  {workerInfo.recent_jobs.slice(0, 10).map((j) => (
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
