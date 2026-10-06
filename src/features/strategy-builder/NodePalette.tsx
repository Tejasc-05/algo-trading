import {
  Activity,
  ArrowDownCircle,
  ArrowUpCircle,
  Brain,
  GitBranch,
  GripVertical,
  ShieldAlert,
  Target,
  TrendingUp,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { paletteItems } from '@/features/strategy-builder/nodes/StrategyNodes'

const iconMap: Record<string, React.ElementType> = {
  rsi: Activity,
  macd: TrendingUp,
  movingAverage: TrendingUp,
  sentiment: Brain,
  condition: GitBranch,
  buy: ArrowUpCircle,
  sell: ArrowDownCircle,
  stopLoss: ShieldAlert,
  takeProfit: Target,
  openLong: ArrowUpCircle,
  openShort: ArrowDownCircle,
  closePosition: ShieldAlert,
}

const colorMap: Record<string, string> = {
  rsi: 'text-cyan-400',
  macd: 'text-blue-400',
  movingAverage: 'text-indigo-400',
  sentiment: 'text-purple-400',
  condition: 'text-amber-400',
  buy: 'text-emerald-400',
  sell: 'text-red-400',
  stopLoss: 'text-orange-400',
  takeProfit: 'text-teal-400',
  openLong: 'text-emerald-400',
  openShort: 'text-red-400',
  closePosition: 'text-amber-400',
}

interface NodePaletteProps {
  onDragStart: (event: React.DragEvent, nodeType: string, label: string, params: Record<string, string | number>) => void
}

export function NodePalette({ onDragStart }: NodePaletteProps) {
  return (
    <div className="w-56 shrink-0 border-r border-border glass-strong overflow-y-auto">
      <div className="p-4 border-b border-border">
        <h3 className="text-sm font-semibold">Node Library</h3>
        <p className="text-xs text-muted-foreground mt-1">Drag nodes onto the canvas</p>
      </div>
      <div className="p-3 space-y-2">
        {paletteItems.map((item) => {
          const Icon = iconMap[item.type]
          return (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => onDragStart(e, item.type, item.label, { ...item.params })}
              className={cn(
                'flex items-center gap-2 rounded-lg border border-border bg-secondary/30 px-3 py-2.5',
                'cursor-grab active:cursor-grabbing hover:bg-secondary/60 hover:border-primary/20 transition-all'
              )}
            >
              <GripVertical className="h-3 w-3 text-muted-foreground shrink-0" />
              <Icon className={cn('h-4 w-4 shrink-0', colorMap[item.type])} />
              <span className="text-sm font-medium">{item.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
