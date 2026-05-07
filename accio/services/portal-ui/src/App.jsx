import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from 'react-oidc-context'
import LoginPage from './pages/LoginPage.jsx'
import CallbackPage from './pages/CallbackPage.jsx'
import Dashboard from './pages/Dashboard.jsx'
import CatalogPage from './pages/CatalogPage.jsx'
import ProvisionerPage from './pages/ProvisionerPage.jsx'
import ScorecardsPage from './pages/ScorecardsPage.jsx'
import WorkflowsPage from './pages/WorkflowsPage.jsx'
import AuditPage from './pages/AuditPage.jsx'

function ProtectedRoute({ children }) {
  const auth = useAuth()
  if (auth.isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
        <p>Authenticating...</p>
      </div>
    )
  }
  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return children
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/callback" element={<CallbackPage />} />
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/catalog" element={<ProtectedRoute><CatalogPage /></ProtectedRoute>} />
      <Route path="/provisioner" element={<ProtectedRoute><ProvisionerPage /></ProtectedRoute>} />
      <Route path="/scorecards" element={<ProtectedRoute><ScorecardsPage /></ProtectedRoute>} />
      <Route path="/workflows" element={<ProtectedRoute><WorkflowsPage /></ProtectedRoute>} />
      <Route path="/audit" element={<ProtectedRoute><AuditPage /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
