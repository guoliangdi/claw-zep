import React from 'react'
import { useAuthStore } from '@/store/auth'

/** 按钮级 RBAC：无权限则隐藏 children。 */
export const Can: React.FC<{ perm: string; children: React.ReactNode }> = ({ perm, children }) => {
  const hasPermission = useAuthStore((s) => s.hasPermission)
  if (!hasPermission(perm)) return null
  return <>{children}</>
}

export function usePerm() {
  return useAuthStore((s) => s.hasPermission)
}
