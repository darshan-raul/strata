import React, { useEffect } from 'react'
import { useAuth } from 'react-oidc-context'
import { useNavigate } from 'react-router-dom'

export default function CallbackPage() {
  const auth = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (auth.isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [auth.isAuthenticated, navigate])

  if (auth.error) {
    return (
      <div className="loading-screen">
        <p>Authentication error: {auth.error.message}</p>
        <button className="btn-primary" onClick={() => navigate('/login')}>
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="loading-screen">
      <div className="loading-spinner" />
      <p>Completing sign-in...</p>
    </div>
  )
}
