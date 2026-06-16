import React, { useState } from 'react'
import { Button, Card, Descriptions, Form, Input, Select, Space, Tag, message } from 'antd'
import { authApi } from '@/api'
import { useAuthStore } from '@/store/auth'
import { useProjectStore } from '@/store/project'

export const ProfilePage: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  const { projects, currentProjectId, setCurrent } = useProjectStore()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

  const changePwd = async () => {
    const v = await form.validateFields()
    setLoading(true)
    try {
      await authApi.changePassword(v.old_password, v.new_password)
      message.success('密码已修改'); form.resetFields()
    } finally { setLoading(false) }
  }

  return (
    <div>
      <div className="cz-page-title">个人中心</div>
      <Card title="账号信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{user?.email}</Descriptions.Item>
          <Descriptions.Item label="系统角色"><Tag color="blue">{user?.system_role}</Tag></Descriptions.Item>
          <Descriptions.Item label="租户ID">{user?.tenant_id || '-'}</Descriptions.Item>
          <Descriptions.Item label="权限数">{user?.permissions.length}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="快速切换项目" style={{ marginBottom: 16 }}>
        <Select style={{ width: 320 }} value={currentProjectId || undefined}
          onChange={(v) => { setCurrent(v); message.success('已切换项目') }}
          options={projects.map((p) => ({ value: p.id, label: p.name }))} />
      </Card>

      <Card title="修改密码">
        <Form form={form} layout="vertical" style={{ maxWidth: 400 }}>
          <Form.Item name="old_password" label="原密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 8 }]}><Input.Password /></Form.Item>
          <Button type="primary" loading={loading} onClick={changePwd}>更新密码</Button>
        </Form>
      </Card>
    </div>
  )
}
