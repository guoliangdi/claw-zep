// 全局类型定义

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface CurrentUser {
  id: string
  email: string
  username: string
  display_name?: string
  system_role: 'super_admin' | 'tenant_admin' | 'member'
  tenant_id?: string
  permissions: string[]
}

export interface Tenant {
  id: string
  name: string
  slug: string
  description?: string
  status: string
  max_projects: number
  max_users: number
  max_memory_mb: number
  max_api_calls_per_day: number
  contact_email?: string
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  tenant_id: string
  name: string
  slug: string
  description?: string
  status: string
  llm_provider?: string
  llm_model?: string
  embedding_model?: string
  kuzu_graph_name: string
  chroma_collection_name: string
  entity_count: number
  relation_count: number
  episode_count: number
  memory_tree_node_count: number
  created_at: string
  updated_at: string
}

export interface ProjectAPIKey {
  id: string
  project_id: string
  name: string
  key_prefix: string
  is_active: boolean
  expires_at?: string
  last_used_at?: string
  created_at: string
}

export interface Episode {
  id: string
  project_id: string
  name?: string
  content: string
  episode_type: string
  status: string
  source: string
  group_id?: string
  extracted_entity_count: number
  extracted_relation_count: number
  valid_from: string
  valid_until?: string
  version: number
  created_at: string
}

export interface GraphNode {
  id: string
  label: string
  type: string
  summary?: string
  valid_from?: string
  valid_until?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  fact?: string
  confidence_score?: number
}

export interface GraphVisualization {
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}

export interface SearchResultItem {
  kind: 'entity' | 'relation' | 'memory_tree'
  id: string
  score: number
  title: string
  content?: string
  valid_from?: string
  valid_until?: string
  metadata: Record<string, any>
}

export interface SearchResponse {
  query: string
  results: SearchResultItem[]
  total: number
  elapsed_ms: number
}

export interface MemoryTreeNode {
  id: string
  tenant_id: string
  project_id: string
  tree_layer: 'source' | 'topic' | 'global'
  status: string
  parent_id?: string
  depth: number
  title: string
  content_markdown?: string
  summary?: string
  topic_label?: string
  entity_refs: string[]
  word_count: number
  child_count: number
  valid_from: string
  valid_until?: string
  version: number
  created_at: string
  updated_at: string
  children?: MemoryTreeNode[]
}

export interface MemoryTreeVersion {
  id: string
  node_id: string
  version_number: number
  title: string
  content_markdown?: string
  changed_by?: string
  change_summary?: string
  created_at: string
}

export interface CausalPath {
  nodes: { kuzu_uuid: string; name: string; entity_type: string }[]
  edges: { relation_type: string; fact?: string; confidence_score?: number }[]
  score: number
  narrative?: string
}

export interface ReasoningResponse {
  question: string
  answer: string
  as_of?: string
  seed_entities: { kuzu_uuid: string; name: string; entity_type: string }[]
  causal_paths: CausalPath[]
  graph: GraphVisualization
  evidence: { node_id: string; title: string; excerpt?: string; score: number }[]
  elapsed_ms: number
}

export interface SnapshotResponse {
  project_id: string
  as_of: string
  stats: { entity_count: number; relation_count: number; memory_tree_node_count: number }
  entities: any[]
  relations: any[]
  memory_tree_nodes: any[]
}

export interface DiffItem {
  change_type: 'added' | 'removed' | 'modified'
  kind: string
  id: string
  name?: string
  before?: any
  after?: any
}

export interface SnapshotDiffResponse {
  project_id: string
  from_time: string
  to_time: string
  added: number
  removed: number
  modified: number
  changes: DiffItem[]
}

export interface EntityLifecycle {
  entity_name?: string
  entity_kuzu_uuid?: string
  total_versions: number
  events: {
    version: number
    valid_from: string
    valid_until?: string
    source: string
    summary?: string
    change: string
    snapshot: any
  }[]
}

export interface User {
  id: string
  email: string
  username: string
  display_name?: string
  system_role: string
  status: string
  tenant_id?: string
  last_login_at?: string
  created_at: string
}

export interface Role {
  id: string
  name: string
  description?: string
  is_system: boolean
  tenant_id?: string
  permissions: Permission[]
  created_at: string
}

export interface Permission {
  id: string
  code: string
  name: string
  resource: string
  action: string
}

export interface Webhook {
  id: string
  project_id: string
  name: string
  target_url: string
  events: string[]
  is_active: boolean
  total_deliveries: number
  failed_deliveries: number
  last_triggered_at?: string
  created_at: string
}

export interface AuditLog {
  id: string
  tenant_id?: string
  project_id?: string
  user_id?: string
  user_email?: string
  action: string
  resource_type?: string
  resource_id?: string
  ip_address?: string
  result: string
  created_at: string
}

export interface Paginated<T> {
  items: T[]
  meta: { page: number; page_size: number; total: number; total_pages: number }
}

export interface Ontology {
  id: string
  project_id: string
  name: string
  description?: string
  entity_types: any[]
  edge_types: any[]
  version: number
  is_current: boolean
  valid_from: string
  created_at: string
}
