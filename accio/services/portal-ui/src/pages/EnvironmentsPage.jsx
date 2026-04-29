import React from 'react'
import Sidebar from '../components/Sidebar.jsx'

const MOCK_ENVIRONMENTS = [
  {
    name: 'dev-eks',
    cloud: 'aws',
    cluster: 'accio-dev-us-east-1',
    locked: false,
    services: [
      { name: 'frontend-app', tag: 'v5.0.2' },
      { name: 'payment-service', tag: 'v2.3.0' },
      { name: 'auth-gateway', tag: 'v1.7.5' },
    ],
    lastDeploy: '12 min ago',
  },
  {
    name: 'staging-eks',
    cloud: 'aws',
    cluster: 'accio-staging-us-east-1',
    locked: false,
    services: [
      { name: 'frontend-app', tag: 'v5.0.1' },
      { name: 'search-service', tag: 'v2.1.3' },
      { name: 'order-service', tag: 'v1.1.9' },
    ],
    lastDeploy: '1 hr ago',
  },
  {
    name: 'prod-eks',
    cloud: 'aws',
    cluster: 'accio-prod-us-east-1',
    locked: false,
    services: [
      { name: 'payment-service', tag: 'v2.4.1' },
      { name: 'notification-svc', tag: 'v3.0.8' },
      { name: 'frontend-app', tag: 'v4.9.0' },
    ],
    lastDeploy: '3 hr ago',
  },
  {
    name: 'dev-gke',
    cloud: 'gcp',
    cluster: 'accio-dev-us-central1',
    locked: false,
    services: [
      { name: 'inventory-api', tag: 'v4.0.0' },
      { name: 'auth-gateway', tag: 'v1.7.5' },
    ],
    lastDeploy: '30 min ago',
  },
  {
    name: 'staging-gke',
    cloud: 'gcp',
    cluster: 'accio-staging-us-central1',
    locked: false,
    services: [
      { name: 'auth-gateway', tag: 'v1.8.0' },
      { name: 'order-service', tag: 'v1.2.0-rc1' },
    ],
    lastDeploy: '5 min ago',
  },
  {
    name: 'prod-gke',
    cloud: 'gcp',
    cluster: 'accio-prod-us-central1',
    locked: true,
    services: [
      { name: 'payment-service', tag: 'v2.4.0' },
      { name: 'frontend-app', tag: 'v4.9.0' },
    ],
    lastDeploy: '6 hr ago',
  },
]

export default function EnvironmentsPage() {
  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Environments</h1>
          <p>Live state of all managed clusters — EKS &amp; GKE</p>
        </div>
        <div className="page-body">
          <div className="env-grid">
            {MOCK_ENVIRONMENTS.map(env => (
              <div className="env-card" key={env.name}>
                <div className="env-card-header">
                  <span className="env-name">{env.name}</span>
                  <span className={`env-cloud-badge ${env.cloud}`}>
                    {env.cloud === 'aws' ? 'EKS' : 'GKE'}
                  </span>
                </div>
                <div className="env-services">
                  {env.services.map(svc => (
                    <div className="env-service-row" key={svc.name}>
                      <span className="env-service-name">{svc.name}</span>
                      <span className="env-service-tag">{svc.tag}</span>
                    </div>
                  ))}
                </div>
                <div className="env-status-bar">
                  <span className={`env-status-indicator ${env.locked ? 'locked' : ''}`} />
                  {env.locked ? 'Locked' : 'Healthy'} · Last deploy {env.lastDeploy}
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
