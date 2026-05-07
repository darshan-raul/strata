import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import { getCatalogServices, getCatalogTeams, createCatalogService } from '../api.js'

const LIFECYCLE_COLOR = {
  production:   'emerald',
  beta:         'sky',
  experimental: 'amber',
  deprecated:   'rose',
}

const LIFECYCLE_BADGE = {
  production:   { bg: 'var(--accent-emerald-glow)', color: 'var(--accent-emerald)' },
  beta:         { bg: 'var(--accent-sky-glow)',     color: 'var(--accent-sky)' },
  experimental: { bg: 'var(--accent-amber-glow)',   color: 'var(--accent-amber)' },
  deprecated:   { bg: 'var(--accent-rose-glow)',    color: 'var(--accent-rose)' },
}

function ServiceCard({ svc }) {
  const badge = LIFECYCLE_BADGE[svc.lifecycle] || LIFECYCLE_BADGE.experimental
  const checks = [
    { key: 'has_docs',       label: 'Docs',       ok: svc.has_docs },
    { key: 'has_slo',        label: 'SLO',        ok: svc.has_slo },
    { key: 'has_api_spec',   label: 'API Spec',   ok: svc.has_api_spec },
    { key: 'has_monitoring', label: 'Monitoring', ok: svc.has_monitoring },
  ]
  const score = checks.filter(c => c.ok).length
  return (
    <div className="panel" style={{ cursor: 'default' }}>
      <div className="panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="panel-title">{svc.name}</span>
          <span style={{ ...badge, padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600 }}>
            {svc.lifecycle}
          </span>
        </div>
        <span className="deploy-tag">{svc.type}</span>
      </div>
      <div style={{ padding: '14px 20px' }}>
        {svc.description && (
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>{svc.description}</p>
        )}
        {svc.language && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
            Lang: <strong style={{ color: 'var(--text-secondary)' }}>{svc.language}</strong>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {checks.map(c => (
            <span key={c.key} style={{
              padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 600,
              background: c.ok ? 'var(--accent-emerald-glow)' : 'rgba(100,116,139,0.15)',
              color: c.ok ? 'var(--accent-emerald)' : 'var(--text-muted)',
            }}>
              {c.ok ? '✓' : '✗'} {c.label}
            </span>
          ))}
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
          Readiness: <strong style={{ color: score === 4 ? 'var(--accent-emerald)' : score >= 2 ? 'var(--accent-amber)' : 'var(--accent-rose)' }}>{score}/4</strong>
        </div>
      </div>
    </div>
  )
}

export default function CatalogPage() {
  const [services, setServices] = useState([])
  const [teams, setTeams]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [tab, setTab]           = useState('services')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm]         = useState({ name: '', description: '', language: '', lifecycle: 'experimental', type: 'service', has_docs: false, has_slo: false, has_api_spec: false, has_monitoring: false })
  const [submitting, setSubmitting] = useState(false)
  const [filter, setFilter] = useState('')

  const load = async () => {
    try {
      const [s, t] = await Promise.all([getCatalogServices(), getCatalogTeams()])
      setServices(s || [])
      setTeams(t || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const submit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await createCatalogService(form)
      setShowForm(false)
      setForm({ name: '', description: '', language: '', lifecycle: 'experimental', type: 'service', has_docs: false, has_slo: false, has_api_spec: false, has_monitoring: false })
      load()
    } catch(err) {
      alert('Error: ' + err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const filtered = services.filter(s =>
    !filter || s.name.toLowerCase().includes(filter.toLowerCase()) || s.lifecycle.toLowerCase().includes(filter.toLowerCase())
  )

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Service Catalog</h1>
          <p>All registered services, libraries and teams across the platform</p>
        </div>
        <div className="page-body">
          <div className="page-actions">
            <div style={{ display: 'flex', gap: 8, flex: 1 }}>
              <button className={`tab-btn ${tab === 'services' ? 'active' : ''}`} onClick={() => setTab('services')}>
                📦 Services ({services.length})
              </button>
              <button className={`tab-btn ${tab === 'teams' ? 'active' : ''}`} onClick={() => setTab('teams')}>
                👥 Teams ({teams.length})
              </button>
            </div>
            {tab === 'services' && (
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="search-input"
                  placeholder="Filter services..."
                  value={filter}
                  onChange={e => setFilter(e.target.value)}
                />
                <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
                  + Register Service
                </button>
              </div>
            )}
          </div>

          {/* Register form */}
          {showForm && tab === 'services' && (
            <div className="panel" style={{ marginBottom: 20 }}>
              <div className="panel-header">
                <span className="panel-title">Register New Service</span>
                <button className="btn-ghost" style={{ padding: '4px 12px', fontSize: 13 }} onClick={() => setShowForm(false)}>✕</button>
              </div>
              <form onSubmit={submit} style={{ padding: '20px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <div>
                  <label className="form-label">Service Name *</label>
                  <input className="form-input" required value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))} placeholder="my-service" />
                </div>
                <div>
                  <label className="form-label">Language</label>
                  <input className="form-input" value={form.language} onChange={e => setForm(p => ({...p, language: e.target.value}))} placeholder="Go, Java, Python..." />
                </div>
                <div style={{ gridColumn: '1/-1' }}>
                  <label className="form-label">Description</label>
                  <input className="form-input" value={form.description} onChange={e => setForm(p => ({...p, description: e.target.value}))} placeholder="What does this service do?" />
                </div>
                <div>
                  <label className="form-label">Lifecycle</label>
                  <select className="form-input" value={form.lifecycle} onChange={e => setForm(p => ({...p, lifecycle: e.target.value}))}>
                    <option>experimental</option><option>beta</option><option>production</option><option>deprecated</option>
                  </select>
                </div>
                <div>
                  <label className="form-label">Type</label>
                  <select className="form-input" value={form.type} onChange={e => setForm(p => ({...p, type: e.target.value}))}>
                    <option>service</option><option>library</option><option>website</option><option>tool</option>
                  </select>
                </div>
                <div style={{ gridColumn: '1/-1', display: 'flex', gap: 20 }}>
                  {['has_docs','has_slo','has_api_spec','has_monitoring'].map(k => (
                    <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
                      <input type="checkbox" checked={form[k]} onChange={e => setForm(p => ({...p, [k]: e.target.checked}))} />
                      {k.replace('has_', '').replace('_', ' ')}
                    </label>
                  ))}
                </div>
                <div style={{ gridColumn: '1/-1', display: 'flex', gap: 10 }}>
                  <button className="btn-primary" type="submit" disabled={submitting}>{submitting ? 'Registering...' : 'Register'}</button>
                  <button className="btn-ghost" type="button" onClick={() => setShowForm(false)}>Cancel</button>
                </div>
              </form>
            </div>
          )}

          {loading ? (
            <div className="loading-screen" style={{ minHeight: 200 }}><div className="loading-spinner" /></div>
          ) : tab === 'services' ? (
            filtered.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
                {filtered.map(svc => <ServiceCard key={svc.id} svc={svc} />)}
              </div>
            ) : (
              <div className="empty-state">No services found. Register one above!</div>
            )
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
              {teams.map(t => (
                <div key={t.id} className="panel">
                  <div className="panel-header">
                    <span className="panel-title">👥 {t.name}</span>
                  </div>
                  <div style={{ padding: '14px 20px', fontSize: 13, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {t.email && <div>📧 {t.email}</div>}
                    {t.slack_channel && <div>💬 {t.slack_channel}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
