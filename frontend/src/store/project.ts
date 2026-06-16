import { create } from 'zustand'
import type { Project } from '@/types'
import { projectApi } from '@/api'

interface ProjectState {
  projects: Project[]
  currentProjectId: string | null
  current: () => Project | undefined
  loadProjects: () => Promise<void>
  setCurrent: (id: string) => void
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProjectId: localStorage.getItem('cz_project_id'),
  current: () => get().projects.find((p) => p.id === get().currentProjectId),
  loadProjects: async () => {
    // 无租户上下文（超管未选租户）时跳过，避免 403
    if (!localStorage.getItem('cz_tenant_id')) {
      set({ projects: [], currentProjectId: null })
      return
    }
    const list = await projectApi.list()
    set({ projects: list })
    // 默认选中第一个项目（若当前未选或已失效）
    const cur = get().currentProjectId
    if (!cur || !list.some((p) => p.id === cur)) {
      const first = list[0]?.id || null
      if (first) localStorage.setItem('cz_project_id', first)
      else localStorage.removeItem('cz_project_id')
      set({ currentProjectId: first })
    }
  },
  setCurrent: (id: string) => {
    localStorage.setItem('cz_project_id', id)
    set({ currentProjectId: id })
  },
}))
