import React, { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Table, Tag, message, Popconfirm } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { tenantApi } from '@/api'
import type { Tenant } from '@/types'

export const TenantsPage: React.FC = () => {
  const [data, setData] = useState<Tenant[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = () => tenantApi.list({ page, page_size: 10 }).then((r) => { setData(r.items); setTotal(r.meta.total) })
  useEffect(() => { load() }, [page])

  const create = async () => {
    const v = await form.validateFields()
    await tenantApi.create(v)
    message.success('租户已创建'); setOpen(false); form.resetFields(); load()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <div className="cz-page-title">租户管理（超级管理员）</div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建租户</Button>
      </div>
      <Table<Tenant> rowKey="id" dataSource={data} pagination={{ current: page, total, pageSize: 10, onChange: setPage }}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '标识', dataIndex: 'slug' },
          { title: '状态', dataIndex: 'status', render: (s) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag> },
          { title: '项目配额', dataIndex: 'max_projects' },
          { title: '用户配额', dataIndex: 'max_users' },
          { title: '内存(MB)', dataIndex: 'max_memory_mb' },
          {
            title: '操作', render: (_, r) => (
              <Popconfirm title="停用该租户?" onConfirm={async () => { await tenantApi.suspend(r.id); load() }}>
                <a>停用</a>
              </Popconfirm>
            ),
          },
        ]} />
      <Modal title="新建租户" open={open} onOk={create} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ max_projects: 10, max_users: 50, max_memory_mb: 1024 }}>
          <Form.Item name="name" label="租户名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="slug" label="标识" rules={[{ required: true, pattern: /^[a-z0-9][a-z0-9\-]*$/ }]}><Input placeholder="acme" /></Form.Item>
          <Form.Item name="max_projects" label="项目配额"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="max_users" label="用户配额"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="max_memory_mb" label="内存配额(MB)"><InputNumber min={1} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="admin_email" label="初始管理员邮箱(可选)"><Input /></Form.Item>
          <Form.Item name="admin_password" label="初始管理员密码(可选)"><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
