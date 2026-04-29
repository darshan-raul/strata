import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from 'react-oidc-context'
import LoginPage from './pages/LoginPage.jsx'
import CallbackPage from './pages/CallbackPage.jsx'
import Dashboard from './pages/Dashboard.jsx'
import DeploymentsPage from './pages/DeploymentsPage.jsx'
import EnvironmentsPage from './pages/EnvironmentsPage.jsx'

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
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/deployments"
        element={
          <ProtectedRoute>
            <DeploymentsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/environments"
        element={
          <ProtectedRoute>
            <EnvironmentsPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
