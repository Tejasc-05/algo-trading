import { create } from 'zustand'
import type { Edge, Node } from '@xyflow/react'
import templates from '@/features/strategy-builder/templates.json'

export type NodeType =
  | 'rsi'
  | 'macd'
  | 'movingAverage'
  | 'buy'
  | 'sell'
  | 'sentiment'
  | 'condition'
  | 'stopLoss'
  | 'takeProfit'
  | 'openLong'
  | 'openShort'
  | 'closePosition'

export interface StrategyNodeData extends Record<string, unknown> {
  label: string
  nodeType: NodeType
  params: Record<string, string | number>
}

interface StrategyState {
  savedStrategyId: string | null
  description: string
  strategyName: string
  nodes: Node<StrategyNodeData>[]
  edges: Edge[]
  isDirty: boolean
  setStrategyName: (name: string) => void
  setNodes: (
    nodes: Node<StrategyNodeData>[] | ((current: Node<StrategyNodeData>[]) => Node<StrategyNodeData>[])
  ) => void
  setEdges: (edges: Edge[] | ((current: Edge[]) => Edge[])) => void
  addNode: (node: Node<StrategyNodeData>) => void
  removeNode: (nodeId: string) => void
  updateNodeParams: (nodeId: string, params: Record<string, string | number>) => void
  loadTemplate: (name: string, nodes: Node<StrategyNodeData>[], edges: Edge[]) => void
  loadSaved: (id: string, name: string, description: string, nodes: Node<StrategyNodeData>[], edges: Edge[]) => void
  setSavedStrategyId: (id: string) => void
  reset: () => void
  markSaved: () => void
}

const initialNodes = structuredClone(templates[1].graph.nodes) as unknown as Node<StrategyNodeData>[]
const initialEdges: Edge[] = structuredClone(templates[1].graph.edges)

export const useStrategyStore = create<StrategyState>((set) => ({
  savedStrategyId: null,
  description: '',
  strategyName: templates[1].name,
  nodes: initialNodes,
  edges: initialEdges,
  isDirty: false,
  setStrategyName: (name) => set({ strategyName: name, isDirty: true }),
  setNodes: (nodes) =>
    set((state) => ({
      nodes: typeof nodes === 'function' ? nodes(state.nodes) : nodes,
      isDirty: true,
    })),
  setEdges: (edges) =>
    set((state) => ({
      edges: typeof edges === 'function' ? edges(state.edges) : edges,
      isDirty: true,
    })),
  addNode: (node) => set((s) => ({ nodes: [...s.nodes, node], isDirty: true })),
  removeNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
      isDirty: true,
    })),
  updateNodeParams: (nodeId, params) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, params } } : n
      ),
      isDirty: true,
    })),
  markSaved: () => set({ isDirty: false }),
  loadTemplate: (name, nodes, edges) => set({ strategyName: name, nodes, edges, description: '', savedStrategyId: null, isDirty: true }),
  loadSaved: (id, name, description, nodes, edges) => set({ savedStrategyId: id, strategyName: name, description, nodes, edges, isDirty: false }),
  setSavedStrategyId: (id) => set({ savedStrategyId: id }),
  reset: () => set({ savedStrategyId: null, description: '', strategyName: templates[1].name,
    nodes: structuredClone(initialNodes), edges: structuredClone(initialEdges), isDirty: false }),
}))
