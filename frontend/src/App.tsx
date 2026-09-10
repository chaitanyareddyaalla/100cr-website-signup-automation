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

  // Real-time Status Stream + Resilient Polling Fallback
  useEffect(() => {
    const batchId = batch?.id
    if (!batchId) {
      setConnectionStatus('disconnected')
      return
    }

    let isActive = true
    let reconnectTimeout: number | null = null

    // Background polling every 2s guarantees continuous metrics even through proxy reconnects
    const pollInterval = window.setInterval(() => {
      if (!isActive) return
      getBatch(batchId)
        .then((b) => {
          if (!isActive) return
          setBatch(b)
          setConnectionStatus('connected')
          if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(b.status)) {
            window.clearInterval(pollInterval)
          }
        })
        .catch(() => {})
    }, 2000)

    function connectToEvents() {
      if (!isActive) return

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
          setConnectionStatus('connected')
          if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(nextBatch.status)) {
            isActive = false
            events.close()
            window.clearInterval(pollInterval)
            setConnectionStatus('disconnected')
          }
        } catch {
          // ignore keepalive
        }
      }

      events.onerror = () => {
        if (!isActive) return
        events.close()
        if (batch?.status && ['COMPLETED', 'FAILED', 'CANCELLED'].includes(batch.status)) {
          return
        }
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
      window.clearInterval(pollInterval)
      if (reconnectTimeout) window.clearTimeout(reconnectTimeout)
      if (events) events.close()
    }
  }, [batch?.id])

  async function handleCreateBatch() {
    const code = referral.trim()
    if (!code) {
      setError('Please enter a referral code first.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const created = await createBatch(code, true)
      setBatch(created)
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

  const runningBatchesCount = batchesList.filter((b) => b.status === 'RUNNING').length
  const queuedBatchesCount = batchesList.filter((b) => b.status === 'QUEUED').length
  const completedBatchesCount = batchesList.filter((b) => b.status === 'COMPLETED').length
  const totalSuccessCount = batchesList.reduce((sum, b) => sum + (b.successful || 0), 0)

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
            <p>Launch referral automation and track real-time signup progress.</p>
          </section>

          {/* Live High-Level Overview Stats Bar */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '16px',
              marginBottom: '24px',
            }}
          >
            <div className="card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(16, 185, 129, 0.15)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.25rem',
                }}
              >
                ⚡
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Tasks Running
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10b981' }}>
                  {runningBatchesCount}
                </div>
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(56, 189, 248, 0.15)',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.25rem',
                }}
              >
                ⏳
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Tasks Queued
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#38bdf8' }}>
                  {queuedBatchesCount}
                </div>
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(99, 102, 241, 0.15)',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.25rem',
                }}
              >
                🎯
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Total Successful Signups
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#a5b4fc' }}>
                  {totalSuccessCount.toLocaleString()}
                </div>
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '12px',
                  background: 'rgba(168, 85, 247, 0.15)',
                  border: '1px solid rgba(168, 85, 247, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.25rem',
                }}
              >
                📊
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Completed (1000/1000)
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#c084fc' }}>
                  {completedBatchesCount}
                </div>
              </div>
            </div>
          </div>

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
                    placeholder="e.g. 100CRCLUBW9PKQ69N"
                    maxLength={100}
                  />
                </div>
              </div>

              <button
                type="button"
                className="btn-primary"
                style={{ width: '100%', marginTop: '8px' }}
                onClick={handleCreateBatch}
                disabled={loading}
              >
                {loading ? 'Launching Task...' : 'Launch Task'}
              </button>

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
                        background: batch.error_message?.toLowerCase().includes('limit')
                          ? 'rgba(245, 158, 11, 0.12)'
                          : 'rgba(239, 68, 68, 0.12)',
                        border: batch.error_message?.toLowerCase().includes('limit')
                          ? '1px solid rgba(245, 158, 11, 0.4)'
                          : '1px solid rgba(239, 68, 68, 0.4)',
                        padding: '12px 16px',
                        borderRadius: '12px',
                        marginBottom: '16px',
                        color: batch.error_message?.toLowerCase().includes('limit') ? '#fcd34d' : '#fca5a5',
                        fontSize: '0.875rem',
                      }}
                    >
                      <strong
                        style={{
                          display: 'block',
                          color: batch.error_message?.toLowerCase().includes('limit') ? '#fbbf24' : '#f87171',
                          marginBottom: '4px',
                        }}
                      >
                        {batch.error_message?.toLowerCase().includes('limit')
                          ? '🎯 Referral Code Limit Reached on Target Site:'
                          : '⚠️ Task Halted:'}
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
                    {(batch.status === 'RUNNING' || batch.status === 'PAUSED' || batch.status === 'QUEUED' || batch.status === 'STOPPING') && (
                      <button
                        type="button"
                        className="btn-danger"
                        onClick={() => handleControl('stop')}
                        disabled={operation !== null}
                      >
                        {operation === 'stop' || batch.status === 'STOPPING' ? 'Stopping...' : 'Stop'}
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
                  Running: <strong style={{ color: '#10b981' }}>{runningBatchesCount}</strong> · Queued: <strong style={{ color: '#38bdf8' }}>{queuedBatchesCount}</strong> · Completed: <strong style={{ color: '#34d399' }}>{completedBatchesCount}</strong> · Total Signups: <strong style={{ color: '#a5b4fc' }}>{totalSuccessCount.toLocaleString()}</strong>
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
                          {b.status === 'FAILED' && b.error_message?.toLowerCase().includes('limit') ? (
                            <div>
                              <span
                                className="status-badge"
                                style={{
                                  background: 'rgba(245, 158, 11, 0.15)',
                                  color: '#fbbf24',
                                  borderColor: 'rgba(245, 158, 11, 0.4)',
                                }}
                                title={b.error_message}
                              >
                                LIMIT REACHED
                              </span>
                              <div
                                style={{
                                  fontSize: '0.6875rem',
                                  color: '#f59e0b',
                                  marginTop: '3px',
                                  fontFamily: 'var(--font-mono)',
                                }}
                                title={b.error_message}
                              >
                                {b.successful} / {b.target} maxed
                              </div>
                            </div>
                          ) : b.status === 'FAILED' ? (
                            <div>
                              <span className="status-badge FAILED" title={b.error_message || 'Batch failed'}>
                                {b.status}
                              </span>
                              {b.error_message && (
                                <div
                                  style={{
                                    fontSize: '0.6875rem',
                                    color: '#f87171',
                                    marginTop: '3px',
                                    maxWidth: '140px',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                  title={b.error_message}
                                >
                                  {b.error_message}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className={`status-badge ${b.status}`}>{b.status}</span>
                          )}
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
                              <>
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                  onClick={() => handleControl('pause', b.id)}
                                >
                                  Pause
                                </button>
                                <button
                                  type="button"
                                  className="btn-danger"
                                  style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                  onClick={() => handleControl('stop', b.id)}
                                >
                                  Stop
                                </button>
                              </>
                            )}
                            {b.status === 'PAUSED' && (
                              <>
                                <button
                                  type="button"
                                  className="btn-primary"
                                  style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                  onClick={() => handleControl('resume', b.id)}
                                >
                                  Resume
                                </button>
                                <button
                                  type="button"
                                  className="btn-danger"
                                  style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                                  onClick={() => handleControl('stop', b.id)}
                                >
                                  Stop
                                </button>
                              </>
                            )}
                            {(b.status === 'QUEUED' || b.status === 'STOPPING') && (
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
