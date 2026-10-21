import { useLocation } from 'react-router-dom'
import { StrategyCanvas } from '@/features/strategy-builder/StrategyCanvas'

export function StrategyBuilderPage() {
  const location = useLocation()
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">Strategy Builder</h2>
        <p className="text-sm text-muted-foreground">
          Drag nodes from the library to design your trading algorithm visually
        </p>
      </div>
      <StrategyCanvas key={location.key} />
    </div>
  )
}
