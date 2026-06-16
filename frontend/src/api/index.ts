import { http } from './client'
import type {
  AuditLog, CurrentUser, Episode, EntityLifecycle, GraphVisualization,
  MemoryTreeNode, MemoryTreeVersion, Ontology, Paginated, Permission, Project,
  ProjectAPIKey, ReasoningResponse, Role, SearchResponse, SnapshotDiffResponse,
  SnapshotResponse, Tenant, TokenResponse, User, Webhook,
} from '@/types'

// ---------- Auth ----------
export const authApi = {
  login: (email: string, password: string) =>
    http.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data),
  me: () => http.get<CurrentUser>('/auth/me').then((r) => r.data),
  changePassword: (old_password: string, new_password: string) =>
    http.post('/auth/change-password', { old_password, new_password }).then((r) => r.data),
}

// ---------- Tenants (super admin) ----------
export const tenantApi = {
  list: (params?: any) =>
    http.get<Paginated<Tenant>>('/tenants', { params }).then((r) => r.data),
  create: (body: any) => http.post<Tenant>('/tenants', body).then((r) => r.data),
  update: (id: string, body: any) => http.patch<Tenant>(`/tenants/${id}`, body).then((r) => r.data),
  suspend: (id: string) => http.post<Tenant>(`/tenants/${id}/suspend`).then((r) => r.data),
}

// ---------- Projects ----------
export const projectApi = {
  list: () => http.get<Project[]>('/projects').then((r) => r.data),
  create: (body: any) => http.post<Project>('/projects', body).then((r) => r.data),
  get: (id: string) => http.get<Project>(`/projects/${id}`).then((r) => r.data),
  update: (id: string, body: any) => http.patch<Project>(`/projects/${id}`, body).then((r) => r.data),
  remove: (id: string) => http.delete(`/projects/${id}`).then((r) => r.data),
  // api keys
  listKeys: (id: string) => http.get<ProjectAPIKey[]>(`/projects/${id}/api-keys`).then((r) => r.data),
  createKey: (id: string, body: any) =>
    http.post<{ id: string; api_key: string; key_prefix: string }>(`/projects/${id}/api-keys`, body).then((r) => r.data),
  revokeKey: (id: string, keyId: string) => http.delete(`/projects/${id}/api-keys/${keyId}`).then((r) => r.data),
  // ontology
  getOntology: (id: string) => http.get<Ontology>(`/projects/${id}/ontology`).then((r) => r.data),
  upsertOntology: (id: string, body: any) => http.put<Ontology>(`/projects/${id}/ontology`, body).then((r) => r.data),
  // members
  listMembers: (id: string) => http.get<any[]>(`/projects/${id}/members`).then((r) => r.data),
  addMember: (id: string, body: any) => http.post(`/projects/${id}/members`, body).then((r) => r.data),
  updateMember: (id: string, mid: string, body: any) => http.patch(`/projects/${id}/members/${mid}`, body).then((r) => r.data),
  removeMember: (id: string, mid: string) => http.delete(`/projects/${id}/members/${mid}`).then((r) => r.data),
}

// ---------- Graph ----------
export const graphApi = {
  episodes: (params?: any) =>
    http.get<Paginated<Episode>>('/graph/episodes', { params }).then((r) => r.data),
  entities: (params?: any) => http.get<Paginated<any>>('/graph/entities', { params }).then((r) => r.data),
  relations: (params?: any) => http.get<Paginated<any>>('/graph/relations', { params }).then((r) => r.data),
  visualization: (params?: any) =>
    http.get<GraphVisualization>('/graph/visualization', { params }).then((r) => r.data),
  deleteEntity: (uuid: string) => http.delete(`/graph/entities/${uuid}`).then((r) => r.data),
}

// ---------- Memory ----------
export const memoryApi = {
  add: (body: any) => http.post('/memory/add', body).then((r) => r.data),
  search: (body: any) => http.post<SearchResponse>('/memory/search', body).then((r) => r.data),
}

// ---------- Playground ----------
export const playgroundApi = {
  ingest: (body: any) => http.post('/playground/ingest', body).then((r) => r.data),
  search: (body: any) => http.post<SearchResponse>('/playground/search', body).then((r) => r.data),
}

// ---------- Temporal ----------
export const temporalApi = {
  snapshot: (body: any) => http.post<SnapshotResponse>('/temporal/snapshot', body).then((r) => r.data),
  diff: (body: any) => http.post<SnapshotDiffResponse>('/temporal/diff', body).then((r) => r.data),
  lifecycle: (body: any) => http.post<EntityLifecycle>('/temporal/lifecycle', body).then((r) => r.data),
}

// ---------- Memory Tree ----------
export const treeApi = {
  tree: (tree_layer: string, as_of?: string) =>
    http.get<MemoryTreeNode[]>('/memory-tree/tree', { params: { tree_layer, as_of } }).then((r) => r.data),
  get: (id: string) => http.get<MemoryTreeNode>(`/memory-tree/nodes/${id}`).then((r) => r.data),
  create: (body: any) => http.post<MemoryTreeNode>('/memory-tree/nodes', body).then((r) => r.data),
  update: (id: string, body: any) => http.patch<MemoryTreeNode>(`/memory-tree/nodes/${id}`, body).then((r) => r.data),
  remove: (id: string) => http.delete(`/memory-tree/nodes/${id}`).then((r) => r.data),
  versions: (id: string) => http.get<MemoryTreeVersion[]>(`/memory-tree/nodes/${id}/versions`).then((r) => r.data),
  rollback: (id: string, v: number) => http.post<MemoryTreeNode>(`/memory-tree/nodes/${id}/rollback/${v}`).then((r) => r.data),
  rebuild: () => http.post('/memory-tree/rebuild').then((r) => r.data),
  exportUrl: '/memory-tree/export',
}

// ---------- Palantir ----------
export const palantirApi = {
  reason: (body: any) => http.post<ReasoningResponse>('/palantir/reason', body).then((r) => r.data),
}

// ---------- Users ----------
export const userApi = {
  list: (params?: any) => http.get<Paginated<User>>('/users', { params }).then((r) => r.data),
  create: (body: any) => http.post<User>('/users', body).then((r) => r.data),
  update: (id: string, body: any) => http.patch<User>(`/users/${id}`, body).then((r) => r.data),
  remove: (id: string) => http.delete(`/users/${id}`).then((r) => r.data),
}

// ---------- RBAC ----------
export const rbacApi = {
  permissions: () => http.get<Permission[]>('/rbac/permissions').then((r) => r.data),
  roles: () => http.get<Role[]>('/rbac/roles').then((r) => r.data),
  createRole: (body: any) => http.post<Role>('/rbac/roles', body).then((r) => r.data),
  updateRole: (id: string, body: any) => http.patch<Role>(`/rbac/roles/${id}`, body).then((r) => r.data),
  deleteRole: (id: string) => http.delete(`/rbac/roles/${id}`).then((r) => r.data),
  assign: (body: any) => http.post('/rbac/assign', body).then((r) => r.data),
  revoke: (id: string) => http.delete(`/rbac/assign/${id}`).then((r) => r.data),
}

// ---------- Webhooks ----------
export const webhookApi = {
  list: () => http.get<Webhook[]>('/webhooks').then((r) => r.data),
  create: (body: any) => http.post<Webhook>('/webhooks', body).then((r) => r.data),
  update: (id: string, body: any) => http.patch<Webhook>(`/webhooks/${id}`, body).then((r) => r.data),
  remove: (id: string) => http.delete(`/webhooks/${id}`).then((r) => r.data),
  deliveries: (id: string) => http.get<any[]>(`/webhooks/${id}/deliveries`).then((r) => r.data),
}

// ---------- Audit ----------
export const auditApi = {
  list: (params?: any) => http.get<Paginated<AuditLog>>('/audit', { params }).then((r) => r.data),
}
