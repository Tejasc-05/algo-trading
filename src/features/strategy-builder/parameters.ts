import type { StrategyNodeData } from '@/store/useStrategyStore'

export interface ParameterField {
  label: string
  min?: number
  max?: number
  integer?: boolean
  options?: string[]
}
const fields: Record<string, ParameterField> = {
  period: { label: 'Period', min: 2, max: 500, integer: true },
  oversold: { label: 'Oversold', min: 0, max: 100 },
  overbought: { label: 'Overbought', min: 0, max: 100 },
  fast: { label: 'Fast period', min: 1, max: 200, integer: true },
  slow: { label: 'Slow period', min: 1, max: 500, integer: true },
  signal: { label: 'Signal period', min: 1, max: 200, integer: true },
  output: { label: 'Output', options: ['macd', 'signal', 'histogram'] },
  operator: { label: 'Operator', options: ['<', '>', '<=', '>=', '==', '!=', 'crosses_above', 'crosses_below'] },
  amount: { label: 'Quantity (base asset)', min: 0 },
  limit_price: { label: 'Limit price', min: 0 },
  percent: { label: 'Percent', min: 0, max: 100 },
  threshold: { label: 'Threshold', min: 0, max: 100 },
  value: { label: 'Compare value' },
  source: { label: 'Source' },
}
export function parameterField(type: string, key: string): ParameterField {
  if (key === 'type') return { label: type === 'movingAverage' ? 'Average type' : 'Order type',
    options: type === 'movingAverage' ? ['SMA', 'EMA'] : ['market', 'limit'] }
  if (key === 'period' && type === 'rsi') return { ...fields.period, max: 200 }
  return fields[key] ?? { label: key }
}
export function parameterError(data: StrategyNodeData, key: string): string | null {
  const field = parameterField(data.nodeType, key)
  const value = data.params[key]
  if (value === '' || value === undefined) return 'Required'
  if (field.options) return field.options.includes(String(value)) ? null : 'Choose a listed option'
  if (key === 'source') return String(value).length <= 64 ? null : 'Maximum 64 characters'
  const number = Number(value)
  if (!Number.isFinite(number)) return 'Enter a finite number'
  if (field.integer && !Number.isInteger(number)) return 'Use a whole number'
  if (['amount', 'limit_price', 'percent'].includes(key) && number <= 0) return 'Must be greater than zero'
  if (field.min !== undefined && number < field.min) return `Minimum ${field.min}`
  if (field.max !== undefined && number > field.max) return `Maximum ${field.max}`
  if (data.nodeType === 'macd' && ['fast', 'slow'].includes(key) && Number(data.params.fast) >= Number(data.params.slow)) return 'Fast must be less than slow'
  if (['oversold', 'overbought'].includes(key) && data.params.oversold !== undefined && data.params.overbought !== undefined && Number(data.params.oversold) >= Number(data.params.overbought)) return 'Oversold must be less than overbought'
  return null
}
export function visibleParameters(data: StrategyNodeData) {
  const params = { ...data.params }
  if (data.nodeType === 'condition') {
    if (String(params.operator).startsWith('crosses_')) delete params.value
    else params.value ??= ''
  }
  if (['buy', 'sell', 'openLong', 'openShort'].includes(data.nodeType)) {
    if (params.type === 'limit') params.limit_price ??= ''
    else delete params.limit_price
  }
  return params
}
