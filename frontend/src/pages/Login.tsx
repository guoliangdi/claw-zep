import React, { useState } from 'react'
import { Button, Card, Form, Input, Typography, message } from 'antd'
import { BranchesOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'

const { Title, Text } = Typography

export const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const [loading, setLoading] = useState(false)

  const onFinish = async (v: { email: string; password: string }) => {
    setLoading(true)
    try {
      await login(v.email, v.password)
      message.success('登录成功')
      navigate('/projects')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'linear-gradient(135deg,#1677ff10,#722ed110)' }}>
      <Card style={{ width: 400, boxShadow: '0 8px 30px rgba(0,0,0,.08)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <BranchesOutlined style={{ fontSize: 40, color: '#1677ff' }} />
          <Title level={3} style={{ margin: '8px 0 0' }}>claw-zep</Title>
          <Text type="secondary">私有化时序知识中台</Text>
        </div>
        <Form layout="vertical" onFinish={onFinish} initialValues={{ email: 'admin@claw-zep.com' }}>
          <Form.Item name="email" rules={[{ required: true, type: 'email', message: '请输入邮箱' }]}>
            <Input size="large" prefix={<UserOutlined />} placeholder="邮箱" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password size="large" prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Button type="primary" size="large" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
          管理员 / 租户 / 普通用户统一入口
        </Text>
      </Card>
    </div>
  )
}
