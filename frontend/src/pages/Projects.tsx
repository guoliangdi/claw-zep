import React, { useEffect, useState } from 'react'
import {
  Button, Card, Drawer, Form, Input, Modal, Space, Table, Tabs, Tag,
  Typography, message, Popconfirm, Alert,
} from 'antd'
import { PlusOutlined, KeyOutlined, ApartmentOutlined } from '@ant-design/icons'
import { projectApi } from '@/api'
import type { Project, ProjectAPIKey } from '@/types'
import { Can } from '@/components/Can'
import { useProjectStore } from '@/store/project'

const { Text } = Typography

export const ProjectsPage: React.FC = () => {
  const [data, setData] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [detail, setDetail] = useState<Project | null>(null)
  const [form] = Form.useForm()
  const reloadStore = useProjectStore((s) => s.loadProjects)

  const load = async () => {
    setLoading(true)
    try { setData(await projectApi.list()) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const onCreate = async () => {
    const v = await form.validateFields()
    await projectApi.create(v)
    message.success('项目已创建')
    setCreateOpen(false); form.resetFields()
    await load(); await reloadStore()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <div className="cz-page-title">项目管理</div>
        <Can perm="project:write">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建项目
          </Button>
        </Can>
      </div>
      <Table<Project>
        rowKey="id" loading={loading} dataSource={data}
        columns={[
          { title: '名称', dataIndex: 'name', render: (t, r) => <a onClick={() => setDetail(r)}>{t}</a> },
          { title: '标识', dataIndex: 'slug' },
          { title: '状态', dataIndex: 'status', render: (s) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
          { title: '实体', dataIndex: 'entity_count' },
          { title: '关系', dataIndex: 'relation_count' },
          { title: 'Episodes', dataIndex: 'episode_count' },
          { title: '记忆树', dataIndex: 'memory_tree_node_count' },
          { title: '创建时间', dataIndex: 'created_at', render: (t) => new Date(t).toLocaleString() },
        ]}
      />

      <Modal title="新建项目" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="slug" label="项目标识" rules={[{ required: true, pattern: /^[a-z0-9][a-z0-9\-_]*$/, message: '小写字母数字' }]}><Input placeholder="my-project" /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="llm_model" label="LLM 模型(可选)"><Input placeholder="gpt-4o-mini" /></Form.Item>
        </Form>
      </Modal>

      <ProjectDetailDrawer project={detail} onClose={() => setDetail(null)} />
    </div>
  )
}

const ProjectDetailDrawer: React.FC<{ project: Project | null; onClose: () => void }> = ({ project, onClose }) => {
  const [keys, setKeys] = useState<ProjectAPIKey[]>([])
  const [newKey, setNewKey] = useState<string | null>(null)
  const [ontology, setOntology] = useState<string>('')

  useEffect(() => {
    if (project) {
      projectApi.listKeys(project.id).then(setKeys).catch(() => {})
      projectApi.getOntology(project.id)
        .then((o) => setOntology(JSON.stringify({ entity_types: o.entity_types, edge_types: o.edge_types }, null, 2)))
        .catch(() => setOntology('{\n  "entity_types": [],\n  "edge_types": []\n}'))
    }
  }, [project])

  const createKey = async () => {
    if (!project) return
    const r = await projectApi.createKey(project.id, { name: 'sdk-key' })
    setNewKey(r.api_key)
    setKeys(await projectApi.listKeys(project.id))
  }

  const saveOntology = async () => {
    if (!project) return
    try {
      const parsed = JSON.parse(ontology)
      await projectApi.upsertOntology(project.id, {
        name: 'default',
        entity_types: parsed.entity_types || [],
        edge_types: parsed.edge_types || [],
      })
      message.success('本体已保存')
    } catch {
      message.error('JSON 格式错误')
    }
  }

  return (
    <Drawer title={project?.name} open={!!project} onClose={onClose} width={640}>
      {project && (
        <Tabs
          items={[
            {
              key: 'info', label: '配置', children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text>ID: <Text code>{project.id}</Text></Text>
                  <Text>Kuzu 图: <Text code>{project.kuzu_graph_name}</Text></Text>
                  <Text>Chroma 集合: <Text code>{project.chroma_collection_name}</Text></Text>
                  <Text>LLM: {project.llm_model || '继承全局'}</Text>
                </Space>
              ),
            },
            {
              key: 'keys', label: <span><KeyOutlined /> API Key</span>, children: (
                <>
                  <Can perm="project:write">
                    <Button type="primary" onClick={createKey} style={{ marginBottom: 12 }}>生成 API Key</Button>
                  </Can>
                  {newKey && <Alert type="success" message="请立即复制（仅显示一次）" description={<Text code copyable>{newKey}</Text>} style={{ marginBottom: 12 }} />}
                  <Table rowKey="id" size="small" dataSource={keys} pagination={false}
                    columns={[
                      { title: '名称', dataIndex: 'name' },
                      { title: '前缀', dataIndex: 'key_prefix' },
                      { title: '状态', dataIndex: 'is_active', render: (a) => <Tag color={a ? 'green' : 'red'}>{a ? '启用' : '停用'}</Tag> },
                      {
                        title: '操作', render: (_, r) => (
                          <Can perm="project:write">
                            <Popconfirm title="确认停用?" onConfirm={async () => { await projectApi.revokeKey(project.id, r.id); setKeys(await projectApi.listKeys(project.id)) }}>
                              <a>停用</a>
                            </Popconfirm>
                          </Can>
                        ),
                      },
                    ]} />
                </>
              ),
            },
            {
              key: 'ontology', label: <span><ApartmentOutlined /> 本体</span>, children: (
                <>
                  <Input.TextArea rows={16} value={ontology} onChange={(e) => setOntology(e.target.value)} style={{ fontFamily: 'monospace' }} />
                  <Can perm="project:write">
                    <Button type="primary" onClick={saveOntology} style={{ marginTop: 12 }}>保存本体</Button>
                  </Can>
                </>
              ),
            },
          ]}
        />
      )}
    </Drawer>
  )
}
