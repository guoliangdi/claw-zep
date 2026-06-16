import React, { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/store/auth'

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loadMe } = useAuthStore()
  const [ready, setReady] = useState(false)
  const hasToken = !!localStorage.getItem('cz_access_token')

  useEffect(() => {
    if (hasToken && !user) {
      loadMe().finally(() => setReady(true))
    } else {
      setReady(true)
    }
  }, [])

  if (!hasToken) return <Navigate to="/login" replace />
  if (!ready) return <Spin style={{ display: 'block', marginTop: 120 }} size="large" />
  return <>{children}</>
}
