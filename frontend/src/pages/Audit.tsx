import React, { useEffect, useState } from 'react'
import { DatePicker, Input, Select, Space, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { auditApi } from '@/api'
import type { AuditLog } from '@/types'

const { RangePicker } = DatePicker

export const AuditPage: React.FC = () => {
  const [data, setData] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<any>({})

  const load = () => auditApi.list({ page, page_size: 15, ...filters }).then((r) => { setData(r.items); setTotal(r.meta.total) })
  useEffect(() => { load() }, [page, filters])

  return (
    <div>
      <div className="cz-page-title">审计日志</div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search allowClear placeholder="动作 (如 auth.login)" style={{ width: 200 }}
          onSearch={(v) => setFilters((f: any) => ({ ...f, action: v || undefined }))} />
        <Select allowClear placeholder="结果" style={{ width: 120 }}
          onChange={(v) => setFilters((f: any) => ({ ...f, result: v }))}
          options={[{ value: 'success', label: '成功' }, { value: 'failure', label: '失败' }]} />
        <RangePicker showTime onChange={(v) => setFilters((f: any) => ({
          ...f,
          created_at_gte: v?.[0]?.toISOString(),
          created_at_lte: v?.[1]?.toISOString(),
        }))} />
      </Space>
      <Table<AuditLog> rowKey="id" dataSource={data} size="small"
        pagination={{ current: page, total, pageSize: 15, onChange: setPage }}
        columns={[
          { title: '时间', dataIndex: 'created_at', render: (t) => new Date(t).toLocaleString(), width: 180 },
          { title: '动作', dataIndex: 'action', render: (a) => <Tag>{a}</Tag> },
          { title: '用户', dataIndex: 'user_email' },
          { title: '资源', render: (_, r) => r.resource_type ? `${r.resource_type}:${(r.resource_id || '').slice(0, 8)}` : '-' },
          { title: '结果', dataIndex: 'result', render: (s) => <Tag color={s === 'success' ? 'green' : 'red'}>{s}</Tag> },
          { title: 'IP', dataIndex: 'ip_address' },
        ]} />
    </div>
  )
}
