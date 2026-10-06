import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import {
  Activity,
  ArrowDownCircle,
  ArrowUpCircle,
  Brain,
  GitBranch,
  ShieldAlert,
  Target,
  TrendingUp,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { useStrategyStore, type StrategyNodeData } from '@/store/useStrategyStore'
import { parameterField, parameterError, visibleParameters } from '../parameters'

const nodeStyles: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
  rsi: { icon: Activity, color: 'text-cyan-400', bg: 'from-cyan-500/20 to-cyan-500/5 border-cyan-500/30' },
  macd: { icon: TrendingUp, color: 'text-blue-400', bg: 'from-blue-500/20 to-blue-500/5 border-blue-500/30' },
  movingAverage: { icon: TrendingUp, color: 'text-indigo-400', bg: 'from-indigo-500/20 to-indigo-500/5 border-indigo-500/30' },
  buy: { icon: ArrowUpCircle, color: 'text-emerald-400', bg: 'from-emerald-500/20 to-emerald-500/5 border-emerald-500/30' },
  sell: { icon: ArrowDownCircle, color: 'text-red-400', bg: 'from-red-500/20 to-red-500/5 border-red-500/30' },
  sentiment: { icon: Brain, color: 'text-purple-400', bg: 'from-purple-500/20 to-purple-500/5 border-purple-500/30' },
  condition: { icon: GitBranch, color: 'text-amber-400', bg: 'from-amber-500/20 to-amber-500/5 border-amber-500/30' },
  stopLoss: { icon: ShieldAlert, color: 'text-orange-400', bg: 'from-orange-500/20 to-orange-500/5 border-orange-500/30' },
  takeProfit: { icon: Target, color: 'text-teal-400', bg: 'from-teal-500/20 to-teal-500/5 border-teal-500/30' },
  openLong: { icon: ArrowUpCircle, color: 'text-emerald-400', bg: 'from-emerald-500/20 to-emerald-500/5 border-emerald-500/30' },
  openShort: { icon: ArrowDownCircle, color: 'text-red-400', bg: 'from-red-500/20 to-red-500/5 border-red-500/30' },
  closePosition: { icon: ShieldAlert, color: 'text-amber-400', bg: 'from-amber-500/20 to-amber-500/5 border-amber-500/30' },
}

function BaseNode({ id, data, selected }: NodeProps<Node<StrategyNodeData>>) {
  const style = nodeStyles[data.nodeType] ?? nodeStyles.rsi
  const Icon = style.icon
  const { updateNodeParams, removeNode } = useStrategyStore()

  const handleParamChange = (key: string, value: string) => {
    const params = { ...data.params, [key]: value }
    if (key === 'operator') {
      if (value.startsWith('crosses_')) delete params.value
      else params.value ??= 0
    }
    if (key === 'type' && ['buy', 'sell', 'openLong', 'openShort'].includes(data.nodeType)) {
      if (value === 'market') delete params.limit_price
      else params.limit_price ??= ''
    }
    updateNodeParams(id, params)
  }

  return (
    <div
      className={cn(
        'min-w-[180px] rounded-xl border bg-gradient-to-br backdrop-blur-sm transition-shadow relative',
        style.bg,
        selected && 'ring-2 ring-primary shadow-[0_0_20px_rgba(34,211,238,0.2)]'
      )}
    >
      {data.nodeType === 'condition' && String(data.params.operator).startsWith('crosses_') ? <>
        <Handle id="left" type="target" position={Position.Left} style={{ top: '30%' }} />
        <Handle id="right" type="target" position={Position.Left} style={{ top: '75%' }} />
        <span className="absolute -left-8 top-[25%] text-[10px] text-muted-foreground">A</span>
        <span className="absolute -left-8 top-[70%] text-[10px] text-muted-foreground">B</span>
      </> : !['rsi', 'macd', 'movingAverage', 'sentiment'].includes(data.nodeType) && <Handle
        id="target"
        type="target"
        position={Position.Left}
        className="!bg-primary !border-primary !w-3 !h-3"
      />}

      {selected && (
        <button
          type="button"
          onPointerDown={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation()
            removeNode(id)
          }}
          className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full border border-red-500/50 bg-red-500/20 text-[10px] font-bold text-red-200 hover:bg-red-500/30"
          aria-label="Delete node"
        >
          ×
        </button>
      )}

      <div className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <Icon className={cn('h-4 w-4', style.color)} />
          <span className="text-sm font-semibold">{data.label}</span>
        </div>
        <div className="space-y-1.5">
          {Object.entries(visibleParameters(data)).map(([key, value]) => {
            const field = parameterField(data.nodeType, key)
            const error = parameterError({ ...data, params: visibleParameters(data) }, key)
            const inputId = `${id}-${key}`
            const className = 'nodrag nopan ml-auto w-24 rounded border border-white/10 bg-background/60 px-1.5 py-0.5 text-right font-mono text-foreground outline-none focus:border-cyan-400'

            return (
              <div key={key} className="text-[11px]">
                <div className="flex items-center gap-2">
                <label htmlFor={inputId} className="text-muted-foreground min-w-[52px]">{field.label}</label>
                {field.options ? <select id={inputId} aria-label={`${data.label} ${field.label}`} value={String(value)}
                  className={className} onChange={(event) => handleParamChange(key, event.target.value)}>
                  {field.options.map(option => <option key={option} value={option}>{option}</option>)}
                </select> : <input
                  id={inputId}
                  aria-label={`${data.label} ${field.label}`}
                  aria-invalid={!!error}
                  aria-describedby={error ? `${inputId}-error` : undefined}
                  type={key === 'source' ? 'text' : 'number'}
                  value={String(value)}
                  min={field.min} max={field.max} step={field.integer ? 1 : 'any'}
                  onPointerDown={(event) => event.stopPropagation()}
                  onMouseDown={(event) => event.stopPropagation()}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => handleParamChange(key, event.target.value)}
                  className={className}
                />}
                </div>
                {error && <p id={`${inputId}-error`} className="mt-1 text-red-300">{error}</p>}
              </div>
            )
          })}
          {data.nodeType === 'condition' && String(data.params.operator).startsWith('crosses_') &&
            <p className="max-w-48 text-[10px] text-muted-foreground">A crosses B. Connect one series to each input. Reconnect inputs after changing operators.</p>}
        </div>
      </div>

      {!['buy', 'sell', 'stopLoss', 'takeProfit', 'openLong', 'openShort', 'closePosition'].includes(data.nodeType) && <Handle
        id="source"
        type="source"
        position={Position.Right}
        className="!bg-primary !border-primary !w-3 !h-3"
      />}
    </div>
  )
}

export const RsiNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const MacdNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const MovingAverageNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const BuyNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const SellNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const SentimentNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const ConditionNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const StopLossNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />
export const TakeProfitNode = (props: NodeProps<Node<StrategyNodeData>>) => <BaseNode {...props} />

export const nodeTypes = {
  rsi: RsiNode,
  macd: MacdNode,
  movingAverage: MovingAverageNode,
  buy: BuyNode,
  sell: SellNode,
  sentiment: SentimentNode,
  condition: ConditionNode,
  stopLoss: StopLossNode,
  takeProfit: TakeProfitNode,
  openLong: BuyNode,
  openShort: SellNode,
  closePosition: StopLossNode,
}

export const paletteItems = [
  { type: 'rsi', label: 'RSI', params: { period: 14 } },
  { type: 'macd', label: 'MACD', params: { fast: 12, slow: 26, signal: 9, output: 'histogram' } },
  { type: 'movingAverage', label: 'Moving Average', params: { period: 50, type: 'SMA' } },
  { type: 'sentiment', label: 'Sentiment', params: { threshold: 70, source: 'AI' } },
  { type: 'condition', label: 'Condition', params: { operator: '>', value: 0 } },
  { type: 'buy', label: 'Buy Action', params: { amount: 0.1, type: 'market' } },
  { type: 'sell', label: 'Sell Action', params: { amount: 0.1, type: 'market' } },
  { type: 'stopLoss', label: 'Stop Loss', params: { percent: 2 } },
  { type: 'takeProfit', label: 'Take Profit', params: { percent: 5 } },
  { type: 'openLong', label: 'Open Futures Long', params: { amount: 0.001, type: 'market' } },
  { type: 'openShort', label: 'Open Futures Short', params: { amount: 0.001, type: 'market' } },
  { type: 'closePosition', label: 'Close Futures Position', params: {} },
] as const
