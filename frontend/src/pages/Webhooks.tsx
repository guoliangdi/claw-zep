import React, { useEffect, useState } from 'react'
import { Button, Empty, Form, Input, Modal, Select, Switch, Table, Tag, message, Popconfirm } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { webhookApi } from '@/api'
import type { Webhook } from '@/types'
import { Can } from '@/components/Can'
import { useProjectStore } from '@/store/project'

const EVENTS = [
  '*', 'episode.ingested', 'episode.processed', 'entity.created', 'entity.updated',
  'entity.expired', 'relation.created', 'memory_tree.node_created', 'temporal.conflict_resolved',
]

export const WebhooksPage: React.FC = () => {
  const current = useProjectStore((s) => s.currentProjectId)
  const [data, setData] = useState<Webhook[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = () => webhookApi.list().then(setData).catch(() => {})
  useEffect(() => { if (current) load() }, [current])

  const create = async () => {
    const v = await form.validateFields()
    await webhookApi.create(v)
    message.success('Webhook 已创建'); setOpen(false); form.resetFields(); load()
  }

  if (!current) return <Empty description="请先在顶部选择项目" />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <div className="cz-page-title">Webhook 配置</div>
        <Can perm="webhook:manage">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新增 Webhook</Button>
        </Can>
      </div>
      <Table<Webhook> rowKey="id" dataSource={data}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '回调地址', dataIndex: 'target_url', ellipsis: true },
          { title: '订阅事件', dataIndex: 'events', render: (e: string[]) => e.map((x) => <Tag key={x}>{x}</Tag>) },
          { title: '状态', dataIndex: 'is_active', render: (a) => <Tag color={a ? 'green' : 'default'}>{a ? '启用' : '停用'}</Tag> },
          { title: '投递/失败', render: (_, r) => `${r.total_deliveries}/${r.failed_deliveries}` },
          {
            title: '操作', render: (_, r) => (
              <Can perm="webhook:manage">
                <Popconfirm title="删除该 Webhook?" onConfirm={async () => { await webhookApi.remove(r.id); load() }}>
                  <a>删除</a>
                </Popconfirm>
              </Can>
            ),
          },
        ]} />
      <Modal title="新增 Webhook" open={open} onOk={create} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ events: ['*'], is_active: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="target_url" label="回调地址" rules={[{ required: true, type: 'url' }]}><Input placeholder="https://..." /></Form.Item>
          <Form.Item name="events" label="订阅事件">
            <Select mode="multiple" options={EVENTS.map((e) => ({ value: e, label: e }))} />
          </Form.Item>
          <Form.Item name="secret" label="签名密钥(可选)"><Input /></Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
