import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'

const MOCK_DEPLOYMENTS = [
  { id: 'dep-1001', service: 'payment-service', tag: 'v2.4.1', status: 'completed', strategy: 'canary', envs: ['prod-eks', 'prod-gke'], user: 'admin@accio.dev', submitted: '2026-04-28T12:30:00Z' },
  { id: 'dep-1002', service: 'auth-gateway', tag: 'v1.8.0', status: 'running', strategy: 'rolling', envs: ['staging-gke'], user: 'dev@accio.dev', submitted: '2026-04-28T12:25:00Z' },
  { id: 'dep-1003', service: 'notification-svc', tag: 'v3.1.0', status: 'pending', strategy: 'blue-green', envs: ['prod-eks'], user: 'admin@accio.dev', submitted: '2026-04-28T12:18:00Z' },
  { id: 'dep-1004', service: 'frontend-app', tag: 'v5.0.2', status: 'completed', strategy: 'rolling', envs: ['dev-eks'], user: 'dev@accio.dev', submitted: '2026-04-28T11:45:00Z' },
  { id: 'dep-1005', service: 'order-service', tag: 'v1.2.0-rc1', status: 'failed', strategy: 'canary', envs: ['staging-gke'], user: 'admin@accio.dev', submitted: '2026-04-28T10:30:00Z' },
  { id: 'dep-1006', service: 'inventory-api', tag: 'v4.0.0', status: 'completed', strategy: 'rolling', envs: ['dev-eks', 'dev-gke'], user: 'dev@accio.dev', submitted: '2026-04-28T09:15:00Z' },
  { id: 'dep-1007', service: 'search-service', tag: 'v2.1.3', status: 'approved', strategy: 'blue-green', envs: ['staging-eks'], user: 'admin@accio.dev', submitted: '2026-04-28T08:00:00Z' },
]

export default function DeploymentsPage() {
  const [deployments] = useState(MOCK_DEPLOYMENTS)
  const [filter, setFilter] = useState('all')

  const filtered = filter === 'all'
    ? deployments
    : deployments.filter(d => d.status === filter)

  const formatDate = (iso) => {
    const d = new Date(iso)
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Deployments</h1>
          <p>All deployment requests across environments</p>
        </div>
        <div className="page-body">
          <div className="page-actions">
            <button className="btn-primary" id="new-deployment-btn">+ New Deployment</button>
            <button className={`btn-ghost ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
            <button className={`btn-ghost ${filter === 'running' ? 'active' : ''}`} onClick={() => setFilter('running')}>Running</button>
            <button className={`btn-ghost ${filter === 'completed' ? 'active' : ''}`} onClick={() => setFilter('completed')}>Completed</button>
            <button className={`btn-ghost ${filter === 'failed' ? 'active' : ''}`} onClick={() => setFilter('failed')}>Failed</button>
          </div>

          <div className="panel">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Service</th>
                  <th>Image Tag</th>
                  <th>Strategy</th>
                  <th>Environments</th>
                  <th>Submitted By</th>
                  <th>Time</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(d => (
                  <tr key={d.id}>
                    <td style={{ fontFamily: 'monospace', fontSize: '13px', color: 'var(--text-muted)' }}>{d.id}</td>
                    <td style={{ fontWeight: 600 }}>{d.service}</td>
                    <td><span className="deploy-tag">{d.tag}</span></td>
                    <td style={{ textTransform: 'capitalize' }}>{d.strategy}</td>
                    <td>{d.envs.join(', ')}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{d.user}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{formatDate(d.submitted)}</td>
                    <td><span className={`status-badge ${d.status}`}>{d.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  )
}
