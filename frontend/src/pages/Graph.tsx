import React, { useEffect, useState } from 'react'
import { Button, Card, DatePicker, Input, Select, Space, Table, Tabs, Tag, Empty, Descriptions } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { graphApi } from '@/api'
import type { Episode, GraphVisualization } from '@/types'
import { GraphCanvas } from '@/components/GraphCanvas'
import { useProjectStore } from '@/store/project'

export const GraphPage: React.FC = () => {
  const current = useProjectStore((s) => s.currentProjectId)
  if (!current) return <Empty description="请先在顶部选择项目" />
  return (
    <div>
      <div className="cz-page-title">图谱管理</div>
      <Tabs
        items={[
          { key: 'canvas', label: '图谱画布', children: <GraphCanvasTab /> },
          { key: 'episodes', label: 'Episodes', children: <EpisodesTab /> },
          { key: 'entities', label: '实体', children: <EntitiesTab /> },
          { key: 'relations', label: '关系', children: <RelationsTab /> },
        ]}
      />
    </div>
  )
}

const GraphCanvasTab: React.FC = () => {
  const [data, setData] = useState<GraphVisualization>({ nodes: [], edges: [], node_count: 0, edge_count: 0 })
  const [sel, setSel] = useState<{ id: string; label: string } | null>(null)
  const load = () => graphApi.visualization({ limit: 500 }).then(setData).catch(() => {})
  useEffect(() => { load() }, [])
  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <div style={{ flex: 1 }}>
        <Space style={{ marginBottom: 8 }}>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Tag color="blue">节点 {data.node_count}</Tag>
          <Tag color="purple">关系 {data.edge_count}</Tag>
        </Space>
        {data.nodes.length ? (
          <GraphCanvas data={data} onSelectNode={(id, label) => setSel({ id, label })} />
        ) : <Empty description="暂无图谱数据，请在 Playground 写入记忆" />}
      </div>
      <Card title="实体详情" style={{ width: 280 }} size="small">
        {sel ? (
          <Descriptions column={1} size="small">
            <Descriptions.Item label="名称">{sel.label}</Descriptions.Item>
            <Descriptions.Item label="UUID">{sel.id.slice(0, 12)}…</Descriptions.Item>
          </Descriptions>
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击节点查看" />}
      </Card>
    </div>
  )
}

const EpisodesTab: React.FC = () => {
  const [data, setData] = useState<Episode[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<any>({})
  const load = () => graphApi.episodes({ page, page_size: 10, ...filters }).then((r) => { setData(r.items); setTotal(r.meta.total) })
  useEffect(() => { load() }, [page, filters])
  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select allowClear placeholder="状态" style={{ width: 120 }}
          onChange={(v) => setFilters((f: any) => ({ ...f, status: v }))}
          options={['pending', 'processing', 'completed', 'failed'].map((s) => ({ value: s, label: s }))} />
        <Select allowClear placeholder="来源" style={{ width: 140 }}
          onChange={(v) => setFilters((f: any) => ({ ...f, source: v }))}
          options={['user_input', 'openclaw', 'import', 'system'].map((s) => ({ value: s, label: s }))} />
        <Input.Search allowClear placeholder="内容关键词" style={{ width: 200 }}
          onSearch={(v) => setFilters((f: any) => ({ ...f, search: v || undefined }))} />
      </Space>
      <Table<Episode> rowKey="id" dataSource={data}
        pagination={{ current: page, total, pageSize: 10, onChange: setPage }}
        columns={[
          { title: '内容', dataIndex: 'content', ellipsis: true },
          { title: '类型', dataIndex: 'episode_type' },
          { title: '状态', dataIndex: 'status', render: (s) => <Tag color={s === 'completed' ? 'green' : s === 'failed' ? 'red' : 'blue'}>{s}</Tag> },
          { title: '实体', dataIndex: 'extracted_entity_count' },
          { title: '关系', dataIndex: 'extracted_relation_count' },
          { title: '生效时间', dataIndex: 'valid_from', render: (t) => new Date(t).toLocaleString() },
        ]} />
    </>
  )
}

const EntitiesTab: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  useEffect(() => { graphApi.entities({ page, page_size: 10 }).then((r) => { setData(r.items); setTotal(r.meta.total) }) }, [page])
  return (
    <Table rowKey="id" dataSource={data} pagination={{ current: page, total, pageSize: 10, onChange: setPage }}
      columns={[
        { title: '名称', dataIndex: 'name' },
        { title: '类型', dataIndex: 'entity_type', render: (t) => <Tag>{t}</Tag> },
        { title: '摘要', dataIndex: 'summary', ellipsis: true },
        { title: '版本', dataIndex: 'version' },
        { title: '生效', dataIndex: 'valid_from', render: (t) => new Date(t).toLocaleDateString() },
      ]} />
  )
}

const RelationsTab: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  useEffect(() => { graphApi.relations({ page, page_size: 10 }).then((r) => { setData(r.items); setTotal(r.meta.total) }) }, [page])
  return (
    <Table rowKey="id" dataSource={data} pagination={{ current: page, total, pageSize: 10, onChange: setPage }}
      columns={[
        { title: '源', dataIndex: 'source_entity_name' },
        { title: '关系', dataIndex: 'relation_type', render: (t) => <Tag color="purple">{t}</Tag> },
        { title: '目标', dataIndex: 'target_entity_name' },
        { title: '事实', dataIndex: 'fact', ellipsis: true },
        { title: '置信', dataIndex: 'confidence_score' },
      ]} />
  )
}
