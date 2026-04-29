import React from 'react'
import { useAuth } from 'react-oidc-context'
import { Navigate } from 'react-router-dom'

export default function LoginPage() {
  const auth = useAuth()

  if (auth.isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const handleLogin = () => {
    auth.signinRedirect()
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">⚡</div>
          <h1>Accio</h1>
        </div>
        <p className="login-subtitle">
          Internal Deployment Platform<br />
          Ship code with confidence across EKS &amp; GKE
        </p>

        <button className="login-btn" onClick={handleLogin} id="login-button">
          <span>🔐</span>
          Sign in with SSO
        </button>

        <div className="login-divider">secured by dex</div>

        <div className="login-features">
          <div className="login-feature">
            <div className="login-feature-icon">🚀</div>
            <div className="login-feature-text">Multi-Cloud</div>
          </div>
          <div className="login-feature">
            <div className="login-feature-icon">🔄</div>
            <div className="login-feature-text">Auto-Rollback</div>
          </div>
          <div className="login-feature">
            <div className="login-feature-icon">📊</div>
            <div className="login-feature-text">DORA Metrics</div>
          </div>
        </div>
      </div>
    </div>
  )
}
