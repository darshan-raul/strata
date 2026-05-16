import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { logout, getUser } from '../auth-api.js'

const NAV = [
  { section: 'Overview', links: [
    { to: '/', label: 'Dashboard', icon: '📊', end: true },
  ]},
  { section: 'Platform', links: [
    { to: '/catalog',     label: 'Service Catalog',  icon: '📦' },
    { to: '/scorecards',  label: 'Scorecards',        icon: '🏆' },
  ]},
  { section: 'Operations', links: [
    { to: '/provisioner', label: 'Provisioner',       icon: '⚙️' },
    { to: '/workflows',   label: 'Workflows',         icon: '🔄' },
    { to: '/audit',       label: 'Audit Log',         icon: '🔍' },
  ]},
]

export default function Sidebar() {
  const navigate = useNavigate()
  const user = getUser()
  const displayName = user?.name || user?.sub || 'User'
  const initials = displayName.charAt(0).toUpperCase()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">⚡</div>
        <div>
          <h2>Accio</h2>
          <span className="sidebar-brand-sub">IDP Platform</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV.map(group => (
          <React.Fragment key={group.section}>
            <span className="sidebar-section-label">{group.section}</span>
            {group.links.map(link => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <span className="sidebar-link-icon">{link.icon}</span>
                {link.label}
              </NavLink>
            ))}
          </React.Fragment>
        ))}
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