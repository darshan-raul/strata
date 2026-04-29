import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from 'react-oidc-context'
import App from './App.jsx'
import './index.css'

const oidcConfig = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY || 'http://localhost:3000/application/o/accio-portal/',
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID || 'accio-portal',
  redirect_uri: import.meta.env.VITE_OIDC_REDIRECT_URI || 'http://localhost:3000/callback',
  response_type: 'code',
  scope: 'openid profile email',
  post_logout_redirect_uri: 'http://localhost:3000',
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
