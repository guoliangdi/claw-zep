import React, { useState } from 'react'
import { Button, Card, Col, Empty, Input, InputNumber, List, Row, Slider, Space, Tag, Typography, message } from 'antd'
import { playgroundApi } from '@/api'
import type { SearchResponse } from '@/types'
import { useProjectStore } from '@/store/project'

const { TextArea } = Input
const { Text } = Typography

export const PlaygroundPage: React.FC = () => {
  const current = useProjectStore((s) => s.currentProjectId)
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  const [weights, setWeights] = useState({ vector: 0.5, graph: 0.3, tree: 0.2 })
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [ingesting, setIngesting] = useState(false)

  const ingest = async () => {
    if (!text.trim()) return
    setIngesting(true)
    try {
      const r = await playgroundApi.ingest({ content: text, episode_type: 'text', sync: true })
      message.success(`已抽取 ${r.extracted_entities} 实体 / ${r.extracted_relations} 关系`)
      setText('')
    } finally { setIngesting(false) }
  }

  const search = async () => {
    if (!query.trim()) return
    setResult(await playgroundApi.search({
      query, limit: 10,
      vector_weight: weights.vector, graph_weight: weights.graph, tree_weight: weights.tree,
    }))
  }

  if (!current) return <Empty description="请先在顶部选择项目" />

  return (
    <div>
      <div className="cz-page-title">Playground 调试台</div>
      <Row gutter={16}>
        <Col span={12}>
          <Card title="在线入库（同步抽取）" size="small">
            <TextArea rows={8} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="输入文本，将实时抽取实体与关系入库…" />
            <Button type="primary" loading={ingesting} onClick={ingest} style={{ marginTop: 12 }}>抽取入库</Button>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="在线检索（自定义权重）" size="small">
            <Space.Compact style={{ width: '100%' }}>
              <Input value={query} onChange={(e) => setQuery(e.target.value)} onPressEnter={search} placeholder="检索关键词" />
              <Button type="primary" onClick={search}>检索</Button>
            </Space.Compact>
            <div style={{ marginTop: 16 }}>
              {(['vector', 'graph', 'tree'] as const).map((k) => (
                <div key={k}>
                  <Text type="secondary">{k === 'vector' ? '向量权重' : k === 'graph' ? '图谱权重' : '记忆树权重'}：{weights[k]}</Text>
                  <Slider min={0} max={1} step={0.1} value={weights[k]}
                    onChange={(v) => setWeights((w) => ({ ...w, [k]: v }))} />
                </div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>
      {result && (
        <Card title={`检索结果 (${result.total}) · ${result.elapsed_ms}ms`} size="small" style={{ marginTop: 16 }}>
          <List dataSource={result.results} renderItem={(r) => (
            <List.Item>
              <List.Item.Meta
                title={<>{r.title} <Tag color={r.kind === 'entity' ? 'blue' : r.kind === 'relation' ? 'purple' : 'green'}>{r.kind}</Tag></>}
                description={r.content} />
              <Tag>score {r.score}</Tag>
            </List.Item>
          )} />
        </Card>
      )}
    </div>
  )
}
