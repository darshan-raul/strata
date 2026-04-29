import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'

// Mock data for demo — in production these come from the APIs
const MOCK_DEPLOYMENTS = [
  { id: 'dep-001', service: 'payment-service', tag: 'v2.4.1', status: 'completed', env: 'prod-eks', user: 'admin', time: '2 min ago' },
  { id: 'dep-002', service: 'auth-gateway', tag: 'v1.8.0', status: 'running', env: 'staging-gke', user: 'developer', time: '5 min ago' },
  { id: 'dep-003', service: 'notification-svc', tag: 'v3.1.0', status: 'pending', env: 'prod-eks', user: 'admin', time: '12 min ago' },
  { id: 'dep-004', service: 'frontend-app', tag: 'v5.0.2', status: 'completed', env: 'dev-eks', user: 'developer', time: '1 hr ago' },
  { id: 'dep-005', service: 'order-service', tag: 'v1.2.0', status: 'failed', env: 'staging-gke', user: 'admin', time: '2 hr ago' },
]

const MOCK_APPROVALS = [
  { id: 'apr-001', service: 'payment-service', env: 'production', requester: 'developer', time: '3 min ago' },
  { id: 'apr-002', service: 'notification-svc', env: 'production', requester: 'admin', time: '12 min ago' },
]

export default function Dashboard() {
  const [deployments] = useState(MOCK_DEPLOYMENTS)
  const [approvals] = useState(MOCK_APPROVALS)
  const [liveCount, setLiveCount] = useState(47)

  // Simulate live deployment counter
  useEffect(() => {
    const interval = setInterval(() => {
      setLiveCount(prev => prev + Math.floor(Math.random() * 3))
    }, 8000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Dashboard</h1>
          <p>Platform overview — real-time deployment activity</p>
        </div>
        <div className="page-body">
          {/* Stat Cards */}
          <div className="stat-grid">
            <div className="stat-card indigo">
              <div className="stat-card-header">
                <span className="stat-card-label">Total Deployments</span>
                <span className="stat-card-icon">🚀</span>
              </div>
              <div className="stat-card-value">{liveCount}</div>
              <div className="stat-card-change positive">↑ 12% this week</div>
            </div>
            <div className="stat-card emerald">
              <div className="stat-card-header">
                <span className="stat-card-label">Success Rate</span>
                <span className="stat-card-icon">✅</span>
              </div>
              <div className="stat-card-value">96.2%</div>
              <div className="stat-card-change positive">↑ 2.1% from last week</div>
            </div>
            <div className="stat-card amber">
              <div className="stat-card-header">
                <span className="stat-card-label">Avg Lead Time</span>
                <span className="stat-card-icon">⏱️</span>
              </div>
              <div className="stat-card-value">4.2m</div>
              <div className="stat-card-change positive">↓ 18% faster</div>
            </div>
            <div className="stat-card sky">
              <div className="stat-card-header">
                <span className="stat-card-label">Active Environments</span>
                <span className="stat-card-icon">🌐</span>
              </div>
              <div className="stat-card-value">6</div>
              <div className="stat-card-change">3 EKS · 3 GKE</div>
            </div>
          </div>

          {/* Panels */}
          <div className="panel-grid">
            {/* Deployment Feed */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">Recent Deployments</span>
                <span className="panel-badge">Live</span>
              </div>
              <div className="panel-body">
                {deployments.map(d => (
                  <div className="deploy-item" key={d.id}>
                    <div className={`deploy-status-dot ${d.status}`} />
                    <div className="deploy-info">
                      <div className="deploy-service">{d.service}</div>
                      <div className="deploy-meta">{d.env} · {d.user}</div>
                    </div>
                    <span className="deploy-tag">{d.tag}</span>
                    <span className="deploy-time">{d.time}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Approval Queue */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">Approval Queue</span>
                <span className="panel-badge">{approvals.length} pending</span>
              </div>
              <div className="panel-body">
                {approvals.map(a => (
                  <div className="approval-item" key={a.id}>
                    <div className="deploy-status-dot pending" />
                    <div className="approval-info">
                      <div className="approval-service">{a.service} → {a.env}</div>
                      <div className="approval-meta">Requested by {a.requester} · {a.time}</div>
                    </div>
                    <button className="approval-btn approve">Approve</button>
                    <button className="approval-btn reject">Reject</button>
                  </div>
                ))}
                {approvals.length === 0 && (
                  <div className="deploy-item" style={{ justifyContent: 'center', color: 'var(--text-muted)' }}>
                    No pending approvals
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
