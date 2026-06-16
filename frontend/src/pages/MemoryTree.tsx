import React, { useEffect, useMemo, useState } from 'react'
import {
  Button, Card, Empty, Modal, Segmented, Space, Tree, Typography, message, List, Tag,
} from 'antd'
import { DownloadOutlined, HistoryOutlined, ReloadOutlined, SaveOutlined, SyncOutlined } from '@ant-design/icons'
import MDEditor from '@uiw/react-md-editor'
import type { DataNode } from 'antd/es/tree'
import { treeApi } from '@/api'
import type { MemoryTreeNode, MemoryTreeVersion } from '@/types'
import { Can } from '@/components/Can'
import { useProjectStore } from '@/store/project'

const { Text } = Typography
type Layer = 'source' | 'topic' | 'global'

export const MemoryTreePage: React.FC = () => {
  const current = useProjectStore((s) => s.currentProjectId)
  const [layer, setLayer] = useState<Layer>('source')
  const [nodes, setNodes] = useState<MemoryTreeNode[]>([])
  const [selected, setSelected] = useState<MemoryTreeNode | null>(null)
  const [content, setContent] = useState('')
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versions, setVersions] = useState<MemoryTreeVersion[]>([])

  const load = () => treeApi.tree(layer).then(setNodes).catch(() => {})
  useEffect(() => { if (current) load() }, [layer, current])

  const flat = useMemo(() => {
    const map: Record<string, MemoryTreeNode> = {}
    const walk = (ns: MemoryTreeNode[]) => ns.forEach((n) => { map[n.id] = n; if (n.children) walk(n.children) })
    walk(nodes)
    return map
  }, [nodes])

  const toTree = (ns: MemoryTreeNode[]): DataNode[] =>
    ns.map((n) => ({ key: n.id, title: n.title, children: n.children?.length ? toTree(n.children) : undefined }))

  const onSelect = (keys: React.Key[]) => {
    const n = flat[keys[0] as string]
    if (n) { setSelected(n); setContent(n.content_markdown || '') }
  }

  const save = async () => {
    if (!selected) return
    await treeApi.update(selected.id, { content_markdown: content, change_summary: '在线编辑' })
    message.success('已保存（生成新版本）')
    load()
  }

  const showVersions = async () => {
    if (!selected) return
    setVersions(await treeApi.versions(selected.id))
    setVersionsOpen(true)
  }

  const rollback = async (v: number) => {
    if (!selected) return
    await treeApi.rollback(selected.id, v)
    message.success(`已回滚至 v${v}`)
    setVersionsOpen(false); load()
  }

  const rebuild = async () => {
    await treeApi.rebuild()
    message.success('已触发主题聚合与全局摘要')
    load()
  }

  const exportTree = async () => {
    const token = localStorage.getItem('cz_access_token')
    const resp = await fetch(`/api/v1${treeApi.exportUrl}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': localStorage.getItem('cz_tenant_id') || '',
        'X-Project-ID': localStorage.getItem('cz_project_id') || '',
      },
      body: JSON.stringify({ tree_layer: layer, format: 'obsidian' }),
    })
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'memory_tree.zip'; a.click()
    URL.revokeObjectURL(url)
  }

  if (!current) return <Empty description="请先在顶部选择项目" />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="cz-page-title">记忆树 MemoryTree</div>
        <Space>
          <Segmented value={layer} onChange={(v) => setLayer(v as Layer)}
            options={[{ label: '源树', value: 'source' }, { label: '主题树', value: 'topic' }, { label: '全局树', value: 'global' }]} />
          <Button icon={<ReloadOutlined />} onClick={load} />
          <Can perm="memory_tree:write"><Button icon={<SyncOutlined />} onClick={rebuild}>重建聚合</Button></Can>
          <Button icon={<DownloadOutlined />} onClick={exportTree}>导出 Obsidian</Button>
        </Space>
      </div>
      <div style={{ display: 'flex', gap: 16 }}>
        <Card title="树形结构" style={{ width: 320 }} size="small">
          {nodes.length ? <Tree treeData={toTree(nodes)} onSelect={onSelect} defaultExpandAll /> : <Empty description="暂无节点" />}
        </Card>
        <Card
          title={selected ? selected.title : '节点内容'}
          style={{ flex: 1 }} size="small"
          extra={selected && (
            <Space>
              <Tag>v{selected.version}</Tag>
              <Tag color="blue">{selected.tree_layer}</Tag>
              <Button size="small" icon={<HistoryOutlined />} onClick={showVersions}>历史版本</Button>
              <Can perm="memory_tree:write"><Button size="small" type="primary" icon={<SaveOutlined />} onClick={save}>保存</Button></Can>
            </Space>
          )}
        >
          {selected ? (
            <div data-color-mode="light">
              <MDEditor value={content} onChange={(v) => setContent(v || '')} height={420} />
              {selected.entity_refs?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">关联实体：</Text>
                  {selected.entity_refs.map((r) => <Tag key={r}>{r.slice(0, 8)}</Tag>)}
                </div>
              )}
            </div>
          ) : <Empty description="选择左侧节点进行编辑" />}
        </Card>
      </div>

      <Modal title="版本历史" open={versionsOpen} footer={null} onCancel={() => setVersionsOpen(false)}>
        <List dataSource={versions} renderItem={(v) => (
          <List.Item actions={[<Can perm="memory_tree:write" key="r"><a onClick={() => rollback(v.version_number)}>回滚至此</a></Can>]}>
            <List.Item.Meta title={`v${v.version_number} · ${v.title}`}
              description={`${v.change_summary || ''} · ${new Date(v.created_at).toLocaleString()}`} />
          </List.Item>
        )} />
      </Modal>
    </div>
  )
}
