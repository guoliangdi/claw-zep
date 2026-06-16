import React, { useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Select, Space, Table, Tabs, Tag, message, Popconfirm } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { rbacApi, userApi } from '@/api'
import type { Permission, Role, User } from '@/types'
import { Can } from '@/components/Can'

export const UsersPage: React.FC = () => (
  <div>
    <div className="cz-page-title">用户与权限</div>
    <Tabs
      items={[
        { key: 'users', label: '用户', children: <UsersTab /> },
        { key: 'roles', label: '角色 (RBAC)', children: <RolesTab /> },
      ]}
    />
  </div>
)

const UsersTab: React.FC = () => {
  const [data, setData] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = () => userApi.list({ page, page_size: 10 }).then((r) => { setData(r.items); setTotal(r.meta.total) })
  useEffect(() => { load() }, [page])

  const create = async () => {
    const v = await form.validateFields()
    await userApi.create(v)
    message.success('用户已创建'); setOpen(false); form.resetFields(); load()
  }

  return (
    <>
      <Can perm="user:manage">
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ marginBottom: 12 }}>新建用户</Button>
      </Can>
      <Table<User> rowKey="id" dataSource={data} pagination={{ current: page, total, pageSize: 10, onChange: setPage }}
        columns={[
          { title: '邮箱', dataIndex: 'email' },
          { title: '用户名', dataIndex: 'username' },
          { title: '系统角色', dataIndex: 'system_role', render: (r) => <Tag color="blue">{r}</Tag> },
          { title: '状态', dataIndex: 'status', render: (s) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag> },
          {
            title: '操作', render: (_, r) => (
              <Can perm="user:manage">
                <Popconfirm title="停用该用户?" onConfirm={async () => { await userApi.remove(r.id); load() }}>
                  <a>停用</a>
                </Popconfirm>
              </Can>
            ),
          },
        ]} />
      <Modal title="新建用户" open={open} onOk={create} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ system_role: 'member' }}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}><Input /></Form.Item>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 8 }]}><Input.Password /></Form.Item>
          <Form.Item name="system_role" label="系统角色">
            <Select options={[{ value: 'member', label: '普通成员' }, { value: 'tenant_admin', label: '租户管理员' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

const RolesTab: React.FC = () => {
  const [roles, setRoles] = useState<Role[]>([])
  const [perms, setPerms] = useState<Permission[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = () => { rbacApi.roles().then(setRoles); rbacApi.permissions().then(setPerms) }
  useEffect(() => { load() }, [])

  const create = async () => {
    const v = await form.validateFields()
    await rbacApi.createRole(v)
    message.success('角色已创建'); setOpen(false); form.resetFields(); load()
  }

  return (
    <>
      <Can perm="user:manage">
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)} style={{ marginBottom: 12 }}>新建角色</Button>
      </Can>
      <Table<Role> rowKey="id" dataSource={roles} pagination={false}
        columns={[
          { title: '角色', dataIndex: 'name' },
          { title: '内置', dataIndex: 'is_system', render: (b) => b ? <Tag color="gold">系统</Tag> : <Tag>自定义</Tag> },
          { title: '权限', dataIndex: 'permissions', render: (ps: Permission[]) => <span>{ps.length} 项</span> },
          { title: '描述', dataIndex: 'description' },
        ]} />
      <Modal title="新建角色" open={open} onOk={create} onCancel={() => setOpen(false)} destroyOnClose width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="角色名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input /></Form.Item>
          <Form.Item name="permission_codes" label="权限">
            <Select mode="multiple" options={perms.map((p) => ({ value: p.code, label: `${p.name} (${p.code})` }))} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
