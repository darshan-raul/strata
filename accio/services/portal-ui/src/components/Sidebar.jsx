import React from 'react'
import { useAuth } from 'react-oidc-context'
import { NavLink } from 'react-router-dom'

export default function Sidebar() {
  const auth = useAuth()
  const user = auth.user?.profile

  const displayName = user?.name || user?.preferred_username || user?.email || 'User'
  const initials = displayName.charAt(0).toUpperCase()

  const handleLogout = () => {
    auth.removeUser()
    window.location.href = '/login'
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">⚡</div>
        <h2>Accio</h2>
      </div>

      <nav className="sidebar-nav">
        <span className="sidebar-section-label">Overview</span>
        <NavLink to="/" end className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          <span className="sidebar-link-icon">📊</span>
          Dashboard
        </NavLink>

        <span className="sidebar-section-label">Deployment</span>
        <NavLink to="/deployments" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          <span className="sidebar-link-icon">🚀</span>
          Deployments
        </NavLink>
        <NavLink to="/environments" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          <span className="sidebar-link-icon">🌐</span>
          Environments
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-user" onClick={handleLogout} title="Click to sign out">
          <div className="sidebar-avatar">{initials}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{displayName}</div>
            <div className="sidebar-user-role">Sign out</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
