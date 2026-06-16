import React, { useState } from 'react'
import { Button, Card, Empty, Input, List, Space, Tag, Typography, Spin, Row, Col } from 'antd'
import { NodeIndexOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { palantirApi } from '@/api'
import type { ReasoningResponse } from '@/types'
import { GraphCanvas } from '@/components/GraphCanvas'
import { useProjectStore } from '@/store/project'

const { Paragraph, Text } = Typography

export const PalantirPage: React.FC = () => {
  const current = useProjectStore((s) => s.currentProjectId)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<ReasoningResponse | null>(null)

  const run = async () => {
    if (!q.trim()) return
    setLoading(true)
    try { setData(await palantirApi.reason({ question: q, max_hops: 3, max_paths: 20, include_memory_tree: true })) }
    finally { setLoading(false) }
  }

  if (!current) return <Empty description="请先在顶部选择项目" />

  return (
    <div>
      <div className="cz-page-title"><NodeIndexOutlined /> 企业推演工作台</div>
      <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
        <Input
          size="large" value={q} onChange={(e) => setQ(e.target.value)} onPressEnter={run}
          placeholder="输入业务问题，如：A供应商断供会影响哪些产品线？"
        />
        <Button size="large" type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={run}>推演</Button>
      </Space.Compact>

      {loading && <Spin style={{ display: 'block', marginTop: 40 }} size="large" />}
      {data && !loading && (
        <Row gutter={16}>
          <Col span={14}>
            <Card title="因果链路图谱" size="small" style={{ marginBottom: 16 }}>
              {data.graph.nodes.length ? <GraphCanvas data={data.graph} height={360} /> : <Empty description="无关联子图" />}
            </Card>
            <Card title="推演结论" size="small">
              <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{data.answer}</Paragraph>
              <Text type="secondary">耗时 {data.elapsed_ms}ms · 种子实体 {data.seed_entities.length}</Text>
            </Card>
          </Col>
          <Col span={10}>
            <Card title={`因果传导链路 (${data.causal_paths.length})`} size="small" style={{ marginBottom: 16 }}>
              <List
                size="small" dataSource={data.causal_paths}
                renderItem={(p, i) => (
                  <List.Item>
                    <div>
                      <Tag color="purple">#{i + 1}</Tag>
                      <Tag color="blue">置信 {p.score}</Tag>
                      <div style={{ marginTop: 4 }}>{p.narrative}</div>
                    </div>
                  </List.Item>
                )}
                locale={{ emptyText: '未发现因果链路' }}
              />
            </Card>
            <Card title="记忆树证据溯源" size="small">
              <List
                size="small" dataSource={data.evidence}
                renderItem={(e) => (
                  <List.Item>
                    <List.Item.Meta title={e.title} description={e.excerpt} />
                    <Tag>{e.score.toFixed(2)}</Tag>
                  </List.Item>
                )}
                locale={{ emptyText: '无关联记忆树片段' }}
              />
            </Card>
          </Col>
        </Row>
      )}
    </div>
  )
}
