const AUTH = import.meta.env.VITE_AUTH_URL || 'http://localhost:8086'

function getToken() {
  return localStorage.getItem('accio_token')
}

function setToken(token) {
  localStorage.setItem('accio_token', token)
}

function clearToken() {
  localStorage.removeItem('accio_token')
}

function parseJwt(token) {
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(window.atob(base64))
  } catch {
    return null
  }
}

export function getUser() {
  const token = getToken()
  if (!token) return null
  const claims = parseJwt(token)
  if (!claims) return null
  if (claims.exp * 1000 < Date.now()) {
    clearToken()
    return null
  }
  return claims
}

export function isAuthenticated() {
  return !!getUser()
}

export async function login(username, password) {
  const res = await fetch(`${AUTH}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: 'Login failed' }))
    throw new Error(err.message || 'Login failed')
  }
  const data = await res.json()
  setToken(data.token)
  return data.user
}

export function logout() {
  clearToken()
}

export function authHeader() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}