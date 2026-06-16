import React, { useEffect, useRef } from 'react'
import cytoscape, { Core } from 'cytoscape'
import type { GraphVisualization } from '@/types'

const PALETTE: Record<string, string> = {
  Organization: '#1677ff', Person: '#52c41a', Entity: '#722ed1',
  Product: '#fa8c16', Location: '#13c2c2',
}

export const GraphCanvas: React.FC<{
  data: GraphVisualization
  height?: number
  onSelectNode?: (id: string, label: string) => void
}> = ({ data, height = 520, onSelectNode }) => {
  const ref = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const elements = [
      ...data.nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type } })),
      ...data.edges
        .filter((e) => data.nodes.some((n) => n.id === e.source) && data.nodes.some((n) => n.id === e.target))
        .map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.label } })),
    ]
    const cy = cytoscape({
      container: ref.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: any) => PALETTE[ele.data('type')] || '#8c8c8c',
            label: 'data(label)', color: '#fff', 'font-size': 10,
            'text-valign': 'center', 'text-halign': 'center',
            width: 36, height: 36, 'text-outline-width': 2,
            'text-outline-color': (ele: any) => PALETTE[ele.data('type')] || '#8c8c8c',
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5, 'line-color': '#bfbfbf', 'target-arrow-color': '#bfbfbf',
            'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
            label: 'data(label)', 'font-size': 8, color: '#595959',
            'text-rotation': 'autorotate',
          },
        },
      ],
      layout: { name: 'cose', animate: false, padding: 30 } as any,
    })
    cy.on('tap', 'node', (evt) => onSelectNode?.(evt.target.id(), evt.target.data('label')))
    cyRef.current = cy
    return () => { cy.destroy() }
  }, [data])

  return <div ref={ref} style={{ height, width: '100%', border: '1px solid #f0f0f0', borderRadius: 8 }} />
}
