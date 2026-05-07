import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import { getProvisions, createProvision } from '../api.js'

const STATUS_STYLE = {
  pending:      { dot: 'pending',   label: 'Pending',      color: 'var(--accent-amber)' },
  provisioning: { dot: 'running',   label: 'Provisioning', color: 'var(--accent-sky)' },
  completed:    { dot: 'completed', label: 'Completed',    color: 'var(--accent-emerald)' },
  failed:       { dot: 'failed',    label: 'Failed',       color: 'var(--accent-rose)' },
}

const RESOURCE_TYPES = [
  'kubernetes-namespace', 'postgres-database', 's3-bucket',
  'redis-cache', 'message-queue', 'vpc-network', 'secret-store',
]

const ENVIRONMENTS = ['dev', 'staging', 'production']

function timeAgo(ts) {
  const d = (Date.now() - new Date(ts)) / 1000
  if (d < 60) return `${Math.floor(d)}s ago`
  if (d < 3600) return `${Math.floor(d/60)}m ago`
  return `${Math.floor(d/3600)}h ago`
}

export default function ProvisionerPage() {
  const [requests, setRequests] = useState([])
  const [loading, setLoading]   = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm]         = useState({ name: '', resource_type: 'kubernetes-namespace', environment: 'dev', requester: 'platform-team' })
  const [submitting, setSubmitting] = useState(false)

  const load = async () => {
    try {
      const data = await getProvisions()
      setRequests(data || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // Poll while any request is in-progress
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await createProvision(form)
      setShowForm(false)
      setForm({ name: '', resource_type: 'kubernetes-namespace', environment: 'dev', requester: 'platform-team' })
      load()
    } catch(err) {
      alert('Error: ' + err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const counts = requests.reduce((acc, r) => { acc[r.status] = (acc[r.status]||0)+1; return acc }, {})

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Resource Provisioner</h1>
          <p>Request and track infrastructure provisioning across environments</p>
        </div>
        <div className="page-body">
          {/* Summary pills */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            {Object.entries(STATUS_STYLE).map(([k, v]) => (
              <div key={k} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 16px', background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)',
                fontSize: 13,
              }}>
                <div className={`deploy-status-dot ${v.dot}`} />
                <span style={{ color: 'var(--text-secondary)' }}>{v.label}</span>
                <strong style={{ color: v.color }}>{counts[k] || 0}</strong>
              </div>
            ))}
            <button className="btn-primary" style={{ marginLeft: 'auto' }} onClick={() => setShowForm(!showForm)}>
              + New Request
            </button>
          </div>

          {/* Request form */}
          {showForm && (
            <div className="panel" style={{ marginBottom: 20 }}>
              <div className="panel-header">
                <span className="panel-title">New Provision Request</span>
                <button className="btn-ghost" style={{ padding: '4px 12px', fontSize: 13 }} onClick={() => setShowForm(false)}>✕</button>
              </div>
              <form onSubmit={submit} style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
                <div>
                  <label className="form-label">Resource Name *</label>
                  <input className="form-input" required value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))} placeholder="my-service-db" />
                </div>
                <div>
                  <label className="form-label">Resource Type</label>
                  <select className="form-input" value={form.resource_type} onChange={e => setForm(p => ({...p, resource_type: e.target.value}))}>
                    {RESOURCE_TYPES.map(t => <option key={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="form-label">Environment</label>
                  <select className="form-input" value={form.environment} onChange={e => setForm(p => ({...p, environment: e.target.value}))}>
                    {ENVIRONMENTS.map(e => <option key={e}>{e}</option>)}
                  </select>
                </div>
                <div>
                  <label className="form-label">Requester</label>
                  <input className="form-input" value={form.requester} onChange={e => setForm(p => ({...p, requester: e.target.value}))} placeholder="team-name" />
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                  <button className="btn-primary" type="submit" disabled={submitting}>{submitting ? 'Requesting...' : 'Submit'}</button>
                  <button className="btn-ghost" type="button" onClick={() => setShowForm(false)}>Cancel</button>
                </div>
              </form>
            </div>
          )}

          {/* Request list */}
          {loading ? (
            <div className="loading-screen" style={{ minHeight: 200 }}><div className="loading-spinner" /></div>
          ) : (
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">Provision Requests</span>
                <span className="panel-badge">{requests.length} total</span>
              </div>
              <div className="panel-body">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Resource Type</th>
                      <th>Environment</th>
                      <th>Requester</th>
                      <th>Status</th>
                      <th>Age</th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.map(r => {
                      const s = STATUS_STYLE[r.status] || STATUS_STYLE.pending
                      return (
                        <tr key={r.id}>
                          <td><strong>{r.name}</strong></td>
                          <td><span className="deploy-tag">{r.resource_type}</span></td>
                          <td>
                            <span style={{
                              padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                              background: r.environment === 'production' ? 'var(--accent-rose-glow)' : r.environment === 'staging' ? 'var(--accent-amber-glow)' : 'var(--accent-sky-glow)',
                              color: r.environment === 'production' ? 'var(--accent-rose)' : r.environment === 'staging' ? 'var(--accent-amber)' : 'var(--accent-sky)',
                            }}>
                              {r.environment}
                            </span>
                          </td>
                          <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{r.requester}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <div className={`deploy-status-dot ${s.dot}`} />
                              <span style={{ fontSize: 13, color: s.color }}>{s.label}</span>
                            </div>
                            {r.error_message && (
                              <div style={{ fontSize: 11, color: 'var(--accent-rose)', marginTop: 2 }}>{r.error_message}</div>
                            )}
                          </td>
                          <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{timeAgo(r.created_at)}</td>
                        </tr>
                      )
                    })}
                    {requests.length === 0 && (
                      <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>
                        No requests yet — submit one above
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
