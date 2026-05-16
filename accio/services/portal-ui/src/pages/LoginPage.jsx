import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../auth-api.js'

export default function LoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
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

        <form onSubmit={handleLogin}>
          {error && <div className="login-error">{error}</div>}
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="login-input"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="login-input"
            required
          />
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="login-divider">demo mode — ask admin for credentials</div>

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