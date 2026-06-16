import React, { useEffect, useState } from 'react'
import { Layout, Menu, Select, Dropdown, Avatar, Space, Typography, theme } from 'antd'
import {
  ApartmentOutlined, ApiOutlined, AuditOutlined, BranchesOutlined,
  ClusterOutlined, DeploymentUnitOutlined, ExperimentOutlined, FieldTimeOutlined,
  FolderOutlined, LogoutOutlined, NodeIndexOutlined, ProjectOutlined,
  SettingOutlined, TeamOutlined, UserOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { useProjectStore } from '@/store/project'
import { tenantApi } from '@/api'
import type { Tenant } from '@/types'

const { Header, Sider, Content } = Layout
const { Text } = Typography

interface NavItem {
  key: string
  label: string
  icon: React.ReactNode
  perm?: string
  superOnly?: boolean
}

const NAV: NavItem[] = [
  { key: '/projects', label: '项目管理', icon: <ProjectOutlined /> },
  { key: '/graph', label: '图谱管理', icon: <DeploymentUnitOutlined />, perm: 'graph:read' },
  { key: '/memory-tree', label: '记忆树', icon: <ApartmentOutlined />, perm: 'memory_tree:read' },
  { key: '/temporal', label: '时序快照', icon: <FieldTimeOutlined />, perm: 'temporal:read' },
  { key: '/palantir', label: '企业推演', icon: <NodeIndexOutlined />, perm: 'graph:read' },
  { key: '/playground', label: 'Playground', icon: <ExperimentOutlined />, perm: 'memory:read' },
  { key: '/users', label: '用户权限', icon: <TeamOutlined />, perm: 'user:read' },
  { key: '/webhooks', label: 'Webhook', icon: <ApiOutlined />, perm: 'webhook:manage' },
  { key: '/audit', label: '审计日志', icon: <AuditOutlined />, perm: 'audit:read' },
  { key: '/tenants', label: '租户管理', icon: <ClusterOutlined />, superOnly: true },
]

export const AppLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout, hasPermission } = useAuthStore()
  const { projects, currentProjectId, loadProjects, setCurrent } = useProjectStore()
  const { token } = theme.useToken()

  const isSuper = user?.system_role === 'super_admin'
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState<string | null>(localStorage.getItem('cz_tenant_id'))

  useEffect(() => {
    const init = async () => {
      if (isSuper) {
        // 超级管理员：先加载租户列表，未选则自动选第一个
        try {
          const list = await tenantApi.list({ page_size: 200 })
          setTenants(list.items)
          let tid = localStorage.getItem('cz_tenant_id')
          if (!tid && list.items.length) {
            tid = list.items[0].id
            localStorage.setItem('cz_tenant_id', tid)
            setTenantId(tid)
          }
        } catch { /* ignore */ }
      }
      await loadProjects().catch(() => {})
    }
    init()
  }, [])

  const onTenantChange = (v: string) => {
    localStorage.setItem('cz_tenant_id', v)
    localStorage.removeItem('cz_project_id')
    setTenantId(v)
    window.location.reload()
  }

  const items = NAV.filter((n) => {
    if (n.superOnly) return user?.system_role === 'super_admin'
    if (n.perm) return hasPermission(n.perm)
    return true
  }).map((n) => ({ key: n.key, label: n.label, icon: n.icon }))

  const selectedKey = '/' + (location.pathname.split('/')[1] || 'projects')

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" breakpoint="lg" collapsible>
        <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 18, letterSpacing: 1 }}>
          <BranchesOutlined style={{ marginRight: 8 }} /> claw-zep
        </div>
        <Menu
          theme="dark" mode="inline" selectedKeys={[selectedKey]} items={items}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: token.colorBgContainer, padding: '0 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space>
            {isSuper && (
              <>
                <ClusterOutlined />
                <Text type="secondary">当前租户</Text>
                <Select
                  style={{ minWidth: 180 }}
                  placeholder="选择租户"
                  value={tenantId || undefined}
                  onChange={onTenantChange}
                  options={tenants.map((t) => ({ value: t.id, label: t.name }))}
                  notFoundContent="暂无租户，请先在「租户管理」创建"
                />
              </>
            )}
            <FolderOutlined />
            <Text type="secondary">当前项目</Text>
            <Select
              style={{ minWidth: 200 }}
              placeholder={projects.length ? '选择项目' : '暂无项目'}
              value={currentProjectId || undefined}
              onChange={(v) => { setCurrent(v); window.location.reload() }}
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
            />
          </Space>
          <Dropdown
            menu={{
              items: [
                { key: 'profile', icon: <SettingOutlined />, label: '个人中心',
                  onClick: () => navigate('/profile') },
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录',
                  onClick: () => { logout(); navigate('/login') } },
              ],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{user?.display_name || user?.username}</span>
              <Text type="secondary" style={{ fontSize: 12 }}>{user?.system_role}</Text>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16, padding: 16, background: token.colorBgContainer,
          borderRadius: 8, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
