import React, { useState } from 'react'
import { Button, Card, DatePicker, Empty, Input, Space, Statistic, Table, Tabs, Tag, Timeline, Row, Col } from 'antd'
import dayjs, { Dayjs } from 'dayjs'
import { temporalApi } from '@/api'
import type { EntityLifecycle, SnapshotDiffResponse, SnapshotResponse } from '@/types'
import { useProjectStore } from '@/store/project'

export const TemporalPage: React.FC = () => {
  const current = useProjectStore((s) => s.currentProjectId)
  if (!current) return <Empty description="请先在顶部选择项目" />
  return (
    <div>
      <div className="cz-page-title">时序快照工作台</div>
      <Tabs
        items={[
          { key: 'snap', label: '时间点快照', children: <SnapshotTab /> },
          { key: 'diff', label: '双时间点对比', children: <DiffTab /> },
          { key: 'life', label: '实体生命周期', children: <LifecycleTab /> },
        ]}
      />
    </div>
  )
}

const SnapshotTab: React.FC = () => {
  const [at, setAt] = useState<Dayjs>(dayjs())
  const [data, setData] = useState<SnapshotResponse | null>(null)
  const run = async () => setData(await temporalApi.snapshot({ as_of: at.toISOString(), include_entities: true, include_relations: true, include_memory_tree: true }))
  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <DatePicker showTime value={at} onChange={(v) => v && setAt(v)} />
        <Button type="primary" onClick={run}>生成快照</Button>
      </Space>
      {data && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}><Card><Statistic title="实体" value={data.stats.entity_count} /></Card></Col>
            <Col span={8}><Card><Statistic title="关系" value={data.stats.relation_count} /></Card></Col>
            <Col span={8}><Card><Statistic title="记忆树节点" value={data.stats.memory_tree_node_count} /></Card></Col>
          </Row>
          <Table size="small" rowKey="kuzu_uuid" dataSource={data.entities} title={() => '快照实体'}
            columns={[{ title: '名称', dataIndex: 'name' }, { title: '类型', dataIndex: 'entity_type' }, { title: '版本', dataIndex: 'version' }]} />
        </>
      )}
    </>
  )
}

const DiffTab: React.FC = () => {
  const [from, setFrom] = useState<Dayjs>(dayjs().subtract(1, 'day'))
  const [to, setTo] = useState<Dayjs>(dayjs())
  const [data, setData] = useState<SnapshotDiffResponse | null>(null)
  const run = async () => setData(await temporalApi.diff({ from_time: from.toISOString(), to_time: to.toISOString(), include_entities: true, include_relations: true }))
  const color = (t: string) => (t === 'added' ? 'green' : t === 'removed' ? 'red' : 'orange')
  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <DatePicker showTime value={from} onChange={(v) => v && setFrom(v)} />
        <span>→</span>
        <DatePicker showTime value={to} onChange={(v) => v && setTo(v)} />
        <Button type="primary" onClick={run}>对比差异</Button>
      </Space>
      {data && (
        <>
          <Space style={{ marginBottom: 12 }}>
            <Tag color="green">新增 {data.added}</Tag>
            <Tag color="orange">变更 {data.modified}</Tag>
            <Tag color="red">移除 {data.removed}</Tag>
          </Space>
          <Table size="small" rowKey={(r) => r.id + r.change_type} dataSource={data.changes}
            columns={[
              { title: '变更', dataIndex: 'change_type', render: (t) => <Tag color={color(t)}>{t}</Tag> },
              { title: '类型', dataIndex: 'kind' },
              { title: '名称', dataIndex: 'name' },
            ]} />
        </>
      )}
    </>
  )
}

const LifecycleTab: React.FC = () => {
  const [name, setName] = useState('')
  const [data, setData] = useState<EntityLifecycle | null>(null)
  const run = async () => setData(await temporalApi.lifecycle({ entity_name: name }))
  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Input placeholder="实体名称" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 240 }} onPressEnter={run} />
        <Button type="primary" onClick={run}>查询变更链路</Button>
      </Space>
      {data && (data.events.length ? (
        <Timeline items={data.events.map((e) => ({
          color: e.change === 'created' ? 'green' : e.change === 'expired' ? 'red' : 'blue',
          children: (
            <div>
              <b>v{e.version} · {e.change}</b> <Tag>{e.source}</Tag>
              <div>{e.summary || e.snapshot?.name}</div>
              <small>{new Date(e.valid_from).toLocaleString()}{e.valid_until ? ` → ${new Date(e.valid_until).toLocaleString()}` : ' → 至今'}</small>
            </div>
          ),
        }))} />
      ) : <Empty description="未找到该实体的历史版本" />)}
    </>
  )
}
