import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from 'react-oidc-context'
import App from './App.jsx'
import './index.css'

const oidcConfig = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY || 'http://Strata.localhost:9091',
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID || 'Strata-portal',
  redirect_uri: import.meta.env.VITE_OIDC_REDIRECT_URI || 'http://Strata.localhost:3000/callback',
  response_type: 'code',
  scope: 'openid profile email',
  post_logout_redirect_uri: 'http://Strata.localhost:3000',
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider {...oidcConfig}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
)
