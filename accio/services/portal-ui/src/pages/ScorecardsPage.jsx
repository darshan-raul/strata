import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import { getScorecards, refreshScorecard } from '../api.js'

function gradeColor(g) {
  return { A: 'var(--accent-emerald)', B: 'var(--accent-sky)', C: 'var(--accent-amber)', D: 'var(--accent-amber)', F: 'var(--accent-rose)' }[g] || 'var(--text-muted)'
}

function ScoreBar({ label, value, max = 25 }) {
  const pct = Math.round((value / max) * 100)
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{value}/{max}</span>
      </div>
      <div style={{ height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: pct >= 80 ? 'var(--accent-emerald)' : pct >= 50 ? 'var(--accent-sky)' : pct >= 25 ? 'var(--accent-amber)' : 'var(--accent-rose)',
          borderRadius: 3, transition: 'width 0.6s ease',
        }} />
      </div>
    </div>
  )
}

function ScorecardCard({ sc }) {
  return (
    <div className="panel">
      <div className="panel-header" style={{ gap: 12 }}>
        <span className="panel-title" style={{ fontSize: 14 }}>{sc.service_name || sc.service_id.slice(0, 8)}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          <div style={{
            width: 40, height: 40, borderRadius: '50%',
            background: `conic-gradient(${gradeColor(sc.grade)} ${sc.total_score}%, var(--bg-tertiary) 0)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            position: 'relative',
          }}>
            <div style={{
              position: 'absolute', width: 30, height: 30, borderRadius: '50%',
              background: 'var(--bg-card)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 13, fontWeight: 800, color: gradeColor(sc.grade),
            }}>
              {sc.grade}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: gradeColor(sc.grade) }}>{sc.total_score}</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>/ 100</div>
          </div>
        </div>
      </div>
      <div style={{ padding: '16px 20px' }}>
        <ScoreBar label="Documentation" value={sc.docs_score} />
        <ScoreBar label="Security / API Spec" value={sc.security_score} />
        <ScoreBar label="Reliability (SLO + Monitoring)" value={sc.reliability_score} max={25} />
        <ScoreBar label="Ownership" value={sc.ownership_score} />
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
          Last evaluated: {new Date(sc.evaluated_at).toLocaleString()}
        </div>
      </div>
    </div>
  )
}

export default function ScorecardsPage() {
  const [scorecards, setScorecards] = useState([])
  const [loading, setLoading]       = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [sortBy, setSortBy]         = useState('score')

  const load = async () => {
    try {
      const data = await getScorecards()
      setScorecards(data || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const triggerRefresh = async () => {
    setRefreshing(true)
    try {
      await refreshScorecard()
      setTimeout(load, 2000) // give backend time to compute
    } catch(err) {
      alert('Error: ' + err.message)
    } finally {
      setTimeout(() => setRefreshing(false), 2000)
    }
  }

  const sorted = [...scorecards].sort((a, b) =>
    sortBy === 'score' ? b.total_score - a.total_score
    : sortBy === 'name' ? a.service_name?.localeCompare(b.service_name)
    : a.grade?.localeCompare(b.grade)
  )

  const gradeBreakdown = scorecards.reduce((acc, s) => { acc[s.grade] = (acc[s.grade]||0)+1; return acc }, {})
  const avg = scorecards.length ? Math.round(scorecards.reduce((s, c) => s + c.total_score, 0) / scorecards.length) : 0

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Service Scorecards</h1>
          <p>Maturity and readiness scores across all catalog entries</p>
        </div>
        <div className="page-body">
          {/* Summary row */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            <div className="stat-card indigo" style={{ flex: 1 }}>
              <div className="stat-card-header">
                <span className="stat-card-label">Avg Score</span>
                <span className="stat-card-icon">📊</span>
              </div>
              <div className="stat-card-value">{avg}</div>
              <div className="stat-card-change">{scorecards.length} services scored</div>
            </div>
            {['A','B','C','D','F'].map(g => (
              <div key={g} className="stat-card" style={{ flex: 1, borderTop: `2px solid ${gradeColor(g)}` }}>
                <div className="stat-card-header">
                  <span className="stat-card-label">Grade {g}</span>
                  <span style={{ fontSize: 18, fontWeight: 800, color: gradeColor(g) }}>{g}</span>
                </div>
                <div className="stat-card-value" style={{ color: gradeColor(g) }}>{gradeBreakdown[g] || 0}</div>
              </div>
            ))}
          </div>

          <div className="page-actions">
            <div style={{ display: 'flex', gap: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', alignSelf: 'center' }}>Sort by:</span>
              {['score','name','grade'].map(s => (
                <button key={s} className={`tab-btn ${sortBy === s ? 'active' : ''}`} onClick={() => setSortBy(s)}>
                  {s}
                </button>
              ))}
            </div>
            <button className="btn-primary" onClick={triggerRefresh} disabled={refreshing} style={{ marginLeft: 'auto' }}>
              {refreshing ? '⟳ Refreshing...' : '⟳ Refresh All'}
            </button>
          </div>

          {loading ? (
            <div className="loading-screen" style={{ minHeight: 200 }}><div className="loading-spinner" /></div>
          ) : sorted.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
              {sorted.map(sc => <ScorecardCard key={sc.id} sc={sc} />)}
            </div>
          ) : (
            <div className="empty-state">No scorecards yet. Register services in the Catalog to generate scores.</div>
          )}
        </div>
      </main>
    </div>
  )
}
