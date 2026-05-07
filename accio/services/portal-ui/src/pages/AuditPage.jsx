import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import { getAuditEvents, getAuditStats } from '../api.js'

const ENTITY_COLORS = {
  catalog_service:  { bg: 'var(--accent-indigo-glow)', color: 'var(--accent-indigo)' },
  catalog_team:     { bg: 'rgba(139,92,246,0.15)',     color: '#8b5cf6' },
  provision_request:{ bg: 'var(--accent-sky-glow)',    color: 'var(--accent-sky)' },
  workflow:         { bg: 'var(--accent-emerald-glow)',color: 'var(--accent-emerald)' },
  scorecard:        { bg: 'var(--accent-amber-glow)',  color: 'var(--accent-amber)' },
  system:           { bg: 'rgba(100,116,139,0.15)',    color: 'var(--text-muted)' },
}

function timeAgo(ts) {
  const d = (Date.now() - new Date(ts)) / 1000
  if (d < 60) return `${Math.floor(d)}s ago`
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return new Date(ts).toLocaleDateString()
}

function EventRow({ ev }) {
  const style = ENTITY_COLORS[ev.entity_type] || ENTITY_COLORS.system
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 14,
      padding: '12px 20px', borderBottom: '1px solid rgba(99,102,241,0.05)',
    }}>
      <span style={{
        padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
        whiteSpace: 'nowrap', marginTop: 2, flexShrink: 0,
        background: style.bg, color: style.color,
      }}>
        {ev.entity_type}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--text-secondary)', marginBottom: 2 }}>
          {ev.event_type}
        </div>
        {ev.summary && (
          <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{ev.summary}</div>
        )}
        {ev.entity_id && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
            {ev.entity_id}
          </div>
        )}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
        {timeAgo(ev.created_at)}
      </div>
    </div>
  )
}

export default function AuditPage() {
  const [events, setEvents]     = useState([])
  const [stats, setStats]       = useState(null)
  const [loading, setLoading]   = useState(true)
  const [filter, setFilter]     = useState('')
  const [entityFilter, setEntityFilter] = useState('')

  const load = async () => {
    try {
      const params = entityFilter ? `entity_type=${entityFilter}&limit=200` : 'limit=200'
      const [evs, st] = await Promise.all([getAuditEvents(params), getAuditStats()])
      setEvents(evs || [])
      setStats(st)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [entityFilter])

  const filtered = events.filter(e =>
    !filter ||
    e.event_type?.includes(filter) ||
    e.entity_id?.includes(filter) ||
    e.summary?.toLowerCase().includes(filter.toLowerCase())
  )

  const entityTypes = Object.keys(ENTITY_COLORS).filter(k => k !== 'system')

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Audit Log</h1>
          <p>Every IDP event captured from all services via NATS</p>
        </div>
        <div className="page-body">
          {/* Stats row */}
          {stats && (
            <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
              <div className="stat-card indigo" style={{ flex: 0, minWidth: 140 }}>
                <div className="stat-card-header">
                  <span className="stat-card-label">Total Events</span>
                  <span className="stat-card-icon">🔍</span>
                </div>
                <div className="stat-card-value">{stats.total}</div>
              </div>
              <div className="stat-card emerald" style={{ flex: 0, minWidth: 140 }}>
                <div className="stat-card-header">
                  <span className="stat-card-label">Last 24h</span>
                  <span className="stat-card-icon">📅</span>
                </div>
                <div className="stat-card-value">{stats.last_24h}</div>
              </div>
            </div>
          )}

          <div className="page-actions" style={{ flexWrap: 'wrap', gap: 10 }}>
            {/* Entity type filter */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button
                className={`tab-btn ${!entityFilter ? 'active' : ''}`}
                onClick={() => setEntityFilter('')}
              >All</button>
              {entityTypes.map(t => (
                <button
                  key={t}
                  className={`tab-btn ${entityFilter === t ? 'active' : ''}`}
                  onClick={() => setEntityFilter(entityFilter === t ? '' : t)}
                >
                  {t.replace('_', ' ')}
                </button>
              ))}
            </div>
            <input
              className="search-input"
              placeholder="Search events..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
              style={{ marginLeft: 'auto' }}
            />
          </div>

          <div className="panel" style={{ marginTop: 12 }}>
            <div className="panel-header">
              <span className="panel-title">Event Stream</span>
              <span className="panel-badge live-dot">{filtered.length} events</span>
            </div>
            {loading ? (
              <div style={{ padding: 32, textAlign: 'center' }}><div className="loading-spinner" style={{ margin: '0 auto' }} /></div>
            ) : filtered.length === 0 ? (
              <div className="empty-state">
                No events yet. Trigger a workflow or provision a resource to see activity here.
              </div>
            ) : (
              filtered.map(ev => <EventRow key={ev.id} ev={ev} />)
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
