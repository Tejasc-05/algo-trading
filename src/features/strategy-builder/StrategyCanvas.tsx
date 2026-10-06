import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Play, Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { NodePalette } from '@/features/strategy-builder/NodePalette'
import { nodeTypes } from '@/features/strategy-builder/nodes/StrategyNodes'
import { useStrategyStore, type StrategyNodeData } from '@/store/useStrategyStore'
import { api } from '@/lib/api'
import spotTemplates from './templates.json'
import futuresTemplates from './futures-templates.json'
const templates = [...spotTemplates, ...futuresTemplates]
import { parameterError, visibleParameters } from './parameters'
import { useApi } from '@/hooks/useApi'

let nodeId = 100

export function StrategyCanvas() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const {
    strategyName,
    nodes,
    edges,
    isDirty,
    setStrategyName,
    setNodes,
    setEdges,
    markSaved,
    removeNode,
    loadTemplate,
    loadSaved,
    savedStrategyId,
    setSavedStrategyId,
    description,
  } = useStrategyStore()
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([])
  const [testStatus, setTestStatus] = useState('Ready')
  const [signalOutput, setSignalOutput] = useState<string[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [templateId, setTemplateId] = useState('')
  const [selectedSavedId, setSelectedSavedId] = useState('')
  const savedStrategies = useApi(() => api.strategies.list())
  const [canvasRevision, setCanvasRevision] = useState(0)

  const onNodesChange = useCallback(
    (changes: NodeChange<Node<StrategyNodeData>>[]) => {
      useStrategyStore.setState(state => ({
        nodes: applyNodeChanges(changes, state.nodes),
        isDirty: state.isDirty || changes.some(change => !['dimensions', 'select'].includes(change.type)),
      }))
    },
    [setNodes]
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      useStrategyStore.setState(state => ({ edges: applyEdgeChanges(changes, state.edges),
        isDirty: state.isDirty || changes.some(change => change.type !== 'select') }))
    },
    [setEdges]
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((currentEdges) => addEdge({ ...connection, animated: true }, currentEdges))
    },
    [setEdges]
  )

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      const type = event.dataTransfer.getData('application/reactflow-type')
      const label = event.dataTransfer.getData('application/reactflow-label')
      const paramsStr = event.dataTransfer.getData('application/reactflow-params')

      if (!type || !reactFlowWrapper.current) return

      const params = JSON.parse(paramsStr) as Record<string, string | number>
      const bounds = reactFlowWrapper.current.getBoundingClientRect()
      const position = {
        x: event.clientX - bounds.left - 90,
        y: event.clientY - bounds.top - 40,
      }

      const newNode: Node<StrategyNodeData> = {
        id: `${type}-${nodeId++}`,
        type,
        position,
        data: { label, nodeType: type as StrategyNodeData['nodeType'], params },
      }

      setNodes([...nodes, newNode])
    },
    [nodes, setNodes]
  )

  const onDragStart = (
    event: React.DragEvent,
    nodeType: string,
    label: string,
    params: Record<string, string | number>
  ) => {
    event.dataTransfer.setData('application/reactflow-type', nodeType)
    event.dataTransfer.setData('application/reactflow-label', label)
    event.dataTransfer.setData('application/reactflow-params', JSON.stringify(params))
    event.dataTransfer.effectAllowed = 'move'
  }

  const buildGraphPayload = () => {
    if (!strategyName.trim()) throw new Error('Enter a strategy name')
    return {
      nodes: nodes.map((node) => {
        const params = visibleParameters(node.data)
        for (const key of Object.keys(params)) {
          const error = parameterError({ ...node.data, params }, key)
          if (error) throw new Error(`${node.data.label}: ${key} — ${error}`)
        }
        const numericParams = Object.fromEntries(Object.entries(params).map(([key, value]) =>
          [key, ['type', 'operator', 'source', 'output', 'label'].includes(key) ? value : Number(value)]))
        return { id: node.id, type: node.type, position: node.position,
          data: { ...node.data, params: numericParams } }
      }),
      edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target,
        sourceHandle: edge.sourceHandle, targetHandle: edge.targetHandle, animated: edge.animated })),
    }
  }

  const persistCurrentGraph = async () => {
    const sessionToken = localStorage.getItem('access_token')
    const graph = buildGraphPayload()
    const validation = await api.strategies.validateGraph(graph)
    if (!validation.valid) throw new Error(validation.errors.map((issue: { message: string }) => issue.message).join('; '))
    if (sessionToken !== localStorage.getItem('access_token')) throw new Error('Your session changed')
    const payload = { name: strategyName.trim(), description, graph }
    const result = savedStrategyId
      ? await api.strategies.update(savedStrategyId, payload)
      : await api.strategies.create(payload)
    if (sessionToken !== localStorage.getItem('access_token')) throw new Error('Your session changed; reopen this strategy after signing in')
    setSavedStrategyId(result.id)
    setSelectedSavedId(result.id)
    markSaved()
    window.dispatchEvent(new Event('algoflow:update'))
    return result
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      const result = await persistCurrentGraph()
      setTestStatus(`Saved: ${result.name} (v${result.current_version})`)
    } catch (err) {
      setTestStatus(`Save failed: ${err instanceof Error ? err.message : 'Unable to save'}`)
    } finally { setIsSaving(false) }
  }

  const handleTestRun = async () => {
    setIsExecuting(true)
    setSignalOutput([])
    try {
      // Always persist the graph on screen; execution reads its latest version.
      const strategy = await persistCurrentGraph()
      const validation = await api.strategies.validate(strategy.id)
      if (!validation.valid) throw new Error(validation.errors.map((issue: { message: string }) => issue.message).join('; '))
      const result = await api.strategies.execute(strategy.id)
      const signals = result.signals || []
      setTestStatus(signals.length ? `Executed: ${signals.length} signal(s)` : 'No signals generated')
      setSignalOutput(signals.length ? signals.map((signal: { action: string; node_id: string; params: unknown }) =>
        `${signal.action.toUpperCase()} (${signal.node_id}) — ${JSON.stringify(signal.params)}`)
        : ['No BUY/SELL signals detected on the latest closed candle'])
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to execute'
      setTestStatus(`Execution failed: ${message}`)
      setSignalOutput([`Error: ${message}`])
    } finally { setIsExecuting(false) }
  }

  const applyTemplate = () => {
    const template = templates.find(item => item.id === templateId)
    if (!template) return
    if (isDirty && !window.confirm('Replace the current unsaved graph with this template?')) return
    const graph = structuredClone(template.graph)
    loadTemplate(template.name, graph.nodes as unknown as Node<StrategyNodeData>[], graph.edges)
    setCanvasRevision(revision => revision + 1)
    setSelectedSavedId('')
    setSelectedNodeIds([])
    setSignalOutput([])
    useStrategyStore.setState({ description: template.description })
    setTestStatus('Template loaded — review quantity and risk before saving')
  }

  const openSavedStrategy = async () => {
    if (!selectedSavedId) return
    if (isDirty && !window.confirm('Replace the current unsaved graph with the saved strategy?')) return
    const sessionToken = localStorage.getItem('access_token')
    setIsSaving(true)
    try {
      const strategy = await api.strategies.get(selectedSavedId)
      if (sessionToken !== localStorage.getItem('access_token')) throw new Error('Your session changed')
      const latest = strategy.versions.find((version: { version_number: number }) => version.version_number === strategy.current_version)
      if (!latest) throw new Error('This strategy has no saved graph')
      const graph = structuredClone(latest.graph)
      loadSaved(strategy.id, strategy.name, strategy.description ?? '', graph.nodes, graph.edges)
      setTemplateId('')
      setSelectedNodeIds([])
      setSignalOutput([])
      setCanvasRevision(revision => revision + 1)
      setTestStatus(`Opened: ${strategy.name} (v${strategy.current_version})`)
    } catch (err) {
      setTestStatus(`Open failed: ${err instanceof Error ? err.message : 'Unable to open strategy'}`)
    } finally { setIsSaving(false) }
  }

  const handleDeleteSelected = () => {
    if (!selectedNodeIds.length) return
    selectedNodeIds.forEach((id) => removeNode(id))
    setSelectedNodeIds([])
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return
      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedNodeIds.length > 0) {
        event.preventDefault()
        handleDeleteSelected()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedNodeIds])

  return (
    <div className="flex h-[calc(100vh-8rem)] rounded-xl border border-border overflow-hidden glass">
      <NodePalette onDragStart={onDragStart} />

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-3">
          <label htmlFor="saved-strategy" className="text-sm">My Saved Strategies</label>
          <select id="saved-strategy" value={selectedSavedId} onChange={event => setSelectedSavedId(event.target.value)}
            disabled={savedStrategies.loading || isExecuting || isSaving}
            className="max-w-xs rounded border border-border bg-background px-3 py-2 text-sm">
            <option value="">{savedStrategies.loading ? 'Loading…' : 'Choose a saved strategy'}</option>
            {(savedStrategies.data ?? []).map((strategy: { id: string; name: string }) =>
              <option key={strategy.id} value={strategy.id}>{strategy.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={openSavedStrategy} disabled={!selectedSavedId || isExecuting || isSaving}>Open Strategy</Button>
          {savedStrategies.error ? <p role="alert" className="text-xs text-destructive">Unable to load your strategies.</p>
            : !savedStrategies.loading && savedStrategies.data?.length === 0 && <p className="text-xs text-muted-foreground">No saved strategies yet. Load a template and save it.</p>}
        </div>
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-3">
          <label htmlFor="strategy-template" className="text-sm">Prebuilt strategies</label>
          <select id="strategy-template" className="rounded border border-border bg-background px-3 py-2 text-sm"
            value={templateId} onChange={event => setTemplateId(event.target.value)} disabled={isExecuting || isSaving}>
            <option value="">Choose a template</option>
            {templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={applyTemplate} disabled={!templateId || isExecuting || isSaving}>Load Template</Button>
          <p className="text-xs text-muted-foreground">Editable starting points. Quantity is in base asset units; defaults are examples.</p>
          {templateId && <p className="w-full text-xs text-muted-foreground">{templates.find(item => item.id === templateId)?.description}</p>}
        </div>
        <div className="flex items-center justify-between gap-4 p-4 border-b border-border">
          <div className="flex items-center gap-3 min-w-0">
            <Input
              aria-label="Strategy name"
              maxLength={255}
              disabled={isExecuting || isSaving}
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              className="max-w-xs h-9 font-medium bg-transparent border-none text-base focus-visible:ring-0 px-0"
            />
            {isDirty && <Badge variant="warning">Unsaved</Badge>}
            <Badge variant="secondary">{testStatus}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestRun}
              disabled={isExecuting || isSaving}
            >
              <Play className="h-4 w-4 mr-1" />
              {isExecuting ? 'Running...' : 'Test Run'}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDeleteSelected}
              disabled={!selectedNodeIds.length}
            >
              <Trash2 className="h-4 w-4 mr-1" />
              Delete Selected
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isSaving || isExecuting}>
              <Save className="h-4 w-4" />
              {isSaving ? 'Saving...' : 'Save Strategy'}
            </Button>
          </div>
        </div>

        {/* Signal Output Panel */}
        {signalOutput.length > 0 && (
          <div className="border-b border-border bg-muted/30 p-3 max-h-32 overflow-y-auto">
            <div className="text-xs font-medium text-muted-foreground mb-1">Signal Output</div>
            {signalOutput.map((line, i) => (
              <div key={i} className="text-xs font-mono text-foreground">
                {line}
              </div>
            ))}
          </div>
        )}

        <div ref={reactFlowWrapper} className={`flex-1 ${isExecuting || isSaving ? 'pointer-events-none' : ''}`}>
          <ReactFlow
            key={canvasRevision}
            nodes={nodes}
            nodesDraggable={!isExecuting && !isSaving}
            nodesConnectable={!isExecuting && !isSaving}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onSelectionChange={({ nodes: selectedNodes }) => {
              const nextSelection = selectedNodes.map((node) => node.id)
              setSelectedNodeIds((current) => {
                const currentKey = current.join(',')
                const nextKey = nextSelection.join(',')
                return currentKey === nextKey ? current : nextSelection
              })
            }}
            nodeTypes={nodeTypes}
            fitView
            className="bg-background/50"
            defaultEdgeOptions={{ animated: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(148,163,184,0.1)" />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                const colors: Record<string, string> = {
                  rsi: '#22d3ee',
                  buy: '#10b981',
                  sell: '#ef4444',
                  condition: '#f59e0b',
                }
                return colors[n.type ?? ''] ?? '#6366f1'
              }}
              maskColor="rgba(6, 8, 15, 0.8)"
            />
          </ReactFlow>
        </div>
      </div>
    </div>
  )
}
