import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import { getCatalogStats, getProvisionStats, getWorkflowStats, getAuditStats } from '../api.js'

function StatCard({ label, value, icon, color, sub }) {
  return (
    <div className={`stat-card ${color}`}>
      <div className="stat-card-header">
        <span className="stat-card-label">{label}</span>
        <span className="stat-card-icon">{icon}</span>
      </div>
      <div className="stat-card-value">{value ?? '—'}</div>
      {sub && <div className="stat-card-change">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [catalog, setCatalog]   = useState(null)
  const [prov, setProv]         = useState(null)
  const [wf, setWf]             = useState(null)
  const [audit, setAudit]       = useState(null)
  const [loading, setLoading]   = useState(true)

  const load = async () => {
    try {
      const [c, p, w, a] = await Promise.allSettled([
        getCatalogStats(), getProvisionStats(), getWorkflowStats(), getAuditStats()
      ])
      if (c.status === 'fulfilled') setCatalog(c.value)
      if (p.status === 'fulfilled') setProv(p.value)
      if (w.status === 'fulfilled') setWf(w.value)
      if (a.status === 'fulfilled') setAudit(a.value)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Platform Overview</h1>
          <p>Live metrics across all IDP services</p>
        </div>
        <div className="page-body">
          {loading ? (
            <div className="loading-screen" style={{ minHeight: 200 }}>
              <div className="loading-spinner" />
            </div>
          ) : (
            <>
              <div className="stat-grid">
                <StatCard label="Catalog Services" icon="📦" color="indigo"
                  value={catalog?.total_services ?? '—'}
                  sub={`${catalog?.production ?? 0} production · ${catalog?.teams ?? 0} teams`} />
                <StatCard label="Provisions" icon="⚙️" color="sky"
                  value={prov?.total ?? '—'}
                  sub={`${prov?.provisioning ?? 0} in-progress · ${prov?.failed ?? 0} failed`} />
                <StatCard label="Workflows" icon="🔄" color="emerald"
                  value={wf?.total ?? '—'}
                  sub={`${wf?.running ?? 0} running · ${wf?.completed ?? 0} completed`} />
                <StatCard label="Audit Events" icon="🔍" color="amber"
                  value={audit?.total ?? '—'}
                  sub={`${audit?.last_24h ?? 0} in last 24h`} />
              </div>

              <div className="panel-grid">
                {/* Platform Status */}
                <div className="panel">
                  <div className="panel-header">
                    <span className="panel-title">Service Health</span>
                    <span className="panel-badge live-dot">Live</span>
                  </div>
                  <div className="panel-body">
                    {[
                      { name: 'catalog-service',     port: 8081, color: 'emerald' },
                      { name: 'provisioner-service',  port: 8082, color: 'emerald' },
                      { name: 'scorecard-service',    port: 8083, color: 'emerald' },
                      { name: 'workflow-engine',      port: 8084, color: 'emerald' },
                      { name: 'audit-service',        port: 8085, color: 'emerald' },
                    ].map(svc => (
                      <div className="deploy-item" key={svc.name}>
                        <div className={`deploy-status-dot ${svc.color === 'emerald' ? 'completed' : 'failed'}`} />
                        <div className="deploy-info">
                          <div className="deploy-service">{svc.name}</div>
                          <div className="deploy-meta">localhost:{svc.port}</div>
                        </div>
                        <span className="deploy-tag">running</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Audit event type breakdown */}
                <div className="panel">
                  <div className="panel-header">
                    <span className="panel-title">Event Breakdown</span>
                    <span className="panel-badge">{audit?.total ?? 0} total</span>
                  </div>
                  <div className="panel-body">
                    {audit?.by_type && Object.entries(audit.by_type).slice(0, 7).map(([type, count]) => (
                      <div className="deploy-item" key={type}>
                        <div className="deploy-info">
                          <div className="deploy-service" style={{ fontFamily: 'monospace', fontSize: 13 }}>{type}</div>
                        </div>
                        <span className="deploy-tag">{count}</span>
                      </div>
                    ))}
                    {(!audit?.by_type || Object.keys(audit.by_type).length === 0) && (
                      <div className="empty-state">No events yet — trigger a workflow to see activity</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Catalog lifecycle breakdown */}
              {catalog && (
                <div className="panel" style={{ marginBottom: 24 }}>
                  <div className="panel-header">
                    <span className="panel-title">Catalog Lifecycle Distribution</span>
                    <span className="panel-badge">{catalog.total_services} services</span>
                  </div>
                  <div className="panel-body" style={{ display: 'flex', gap: 0 }}>
                    {[
                      { label: 'Production',    count: catalog.production,    color: 'var(--accent-emerald)' },
                      { label: 'Beta',          count: catalog.beta,          color: 'var(--accent-sky)' },
                      { label: 'Experimental',  count: catalog.experimental,  color: 'var(--accent-amber)' },
                    ].map(item => (
                      <div key={item.label} style={{ flex: 1, padding: '20px 24px', borderRight: '1px solid var(--border-subtle)' }}>
                        <div style={{ fontSize: 28, fontWeight: 700, color: item.color }}>{item.count ?? 0}</div>
                        <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>{item.label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}
