import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const AuthContext = createContext(null)

export const DEMO_LOGIN = { email: 'demo@example.com', password: 'demo-password' }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(getToken()))

  const refresh = useCallback(async () => {
    try {
      setUser(await api('/auth/me'))
    } catch {
      setToken(null) // expired or invalid token
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (getToken()) refresh()
  }, [refresh])

  const login = async (email, password) => {
    const { access_token } = await api('/auth/token', { method: 'POST', form: { username: email, password } })
    setToken(access_token)
    await refresh()
  }

  const signup = async (details) => {
    await api('/auth/register', { method: 'POST', body: details })
    await login(details.email, details.password)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refresh }}>{children}</AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
