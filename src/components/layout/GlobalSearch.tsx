import { getSessionGeneration } from '@/lib/session'
import { useEffect, useId, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowUpRight, Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import { useStrategyStore } from '@/store/useStrategyStore'
import { cn } from '@/utils/cn'

const pages = [
  ['Dashboard', '/dashboard', 'Account overview'],
  ['Strategy Builder', '/strategy-builder', 'Build and edit algorithms'],
  ['Paper Trading', '/paper-trading', 'Simulate spot and futures strategies'],
  ['Live Trading', '/live-trading', 'Exchange connections and futures demo'],
  ['Sentiment Analysis', '/sentiment', 'News and sentiment scores'],
  ['Portfolio', '/portfolio', 'Positions and performance'],
  ['Settings', '/settings', 'Account settings'],
]
const pairs = [['BTC/USDT', 'Bitcoin'], ['ETH/USDT', 'Ethereum'], ['SOL/USDT', 'Solana'],
  ['BNB/USDT', 'BNB'], ['DOGE/USDT', 'Dogecoin'], ['ADA/USDT', 'Cardano']]
interface Result { id: string; label: string; detail: string; kind: 'strategy' | 'pair' | 'page'; target: string }
const normalize = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, '')

export function GlobalSearch() {
  const { searchTerm, setSearchTerm, user } = useAppStore()
  const strategies = useApi(async () => ({ owner: user.email, items: await api.strategies.list() }), [user.email])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const listId = useId()
  const navigate = useNavigate()
  const location = useLocation()
  const query = normalize(searchTerm)
  const match = (text: string) => !query || normalize(text).includes(query)
  const results: Result[] = [
    ...(strategies.data?.owner === user.email ? strategies.data.items : []).filter(s => match(`${s.name} ${s.description ?? ''}`)).slice(0, 6)
      .map(s => ({ id: `strategy-${s.id}`, label: s.name, detail: `Saved strategy · v${s.current_version}`, kind: 'strategy' as const, target: s.id })),
    ...pairs.filter(([symbol, name]) => match(`${symbol} ${name}`)).map(([symbol, name]) => ({
      id: `pair-${symbol}`, label: symbol, detail: `Pair shortcut · ${name} · Prepare paper account`, kind: 'pair' as const, target: symbol })),
    ...pages.filter(([label, , detail]) => match(`${label} ${detail}`)).map(([label, target, detail]) => ({
      id: `page-${target}`, label, detail: `Page · ${detail}`, kind: 'page' as const, target })),
  ].slice(0, 12)
  const customPair = searchTerm.trim().toUpperCase().match(/^([A-Z0-9]{1,12})[/-]([A-Z0-9]{1,12})$/)
  if (customPair && !results.some(r => r.target === `${customPair[1]}/${customPair[2]}`)) {
    const symbol = `${customPair[1]}/${customPair[2]}`
    results.push({ id: `pair-${symbol}`, label: symbol, detail: 'Pair shortcut · Prepare paper account; availability checked on execution', kind: 'pair', target: symbol })
  }
  const currentIndex = Math.min(active, Math.max(results.length - 1, 0))

  useEffect(() => {
    setOpen(false); setSearchTerm(''); setError(''); setActive(0)
  }, [location.key, user.email, setSearchTerm])
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); setOpen(true); input.current?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', shortcut)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', shortcut) }
  }, [])
  useEffect(() => { if (open) input.current?.focus() }, [open])

  async function select(result: Result) {
    if (busy) return
    setError('')
    if (result.kind === 'strategy') {
      setBusy(true)
      const token = getSessionGeneration()
      try {
        const strategy = await api.strategies.get(result.target)
        if (token !== getSessionGeneration()) throw new Error('Your session changed. Search again after signing in.')
        const latest = strategy.versions.find((v: { version_number: number }) => v.version_number === strategy.current_version)
        if (!latest) throw new Error('This strategy has no saved algorithm version.')
        const store = useStrategyStore.getState()
        if (store.isDirty && !window.confirm('Replace your unsaved builder changes with this saved strategy?')) return
        const graph = structuredClone(latest.graph)
        store.loadSaved(strategy.id, strategy.name, strategy.description ?? '', graph.nodes, graph.edges)
        navigate('/strategy-builder')
      } catch (e) { setError(e instanceof Error ? e.message : 'Unable to open strategy'); return }
      finally { setBusy(false) }
    } else if (result.kind === 'pair') {
      navigate(`/paper-trading?symbol=${encodeURIComponent(result.target)}`)
    } else navigate(result.target)
    setOpen(false); setSearchTerm(''); input.current?.blur()
  }

  return <div ref={root} className="relative">
    <button aria-label="Open search" aria-expanded={open} onClick={() => setOpen(!open)} className="md:hidden min-h-11 min-w-11 rounded-lg flex items-center justify-center hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <Search aria-hidden="true" className="h-5 w-5" />
    </button>
    <div className={cn('relative md:block', open ? 'max-md:fixed max-md:top-20 max-md:left-4 max-md:right-4' : 'max-md:hidden')}>
      <Search aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <Input ref={input} role="combobox" aria-label="Search strategies, pairs and pages" aria-autocomplete="list" aria-expanded={open}
        aria-controls={listId} aria-activedescendant={open && results.length ? `${listId}-${currentIndex}` : undefined}
        autoComplete="off" value={searchTerm} readOnly={busy} placeholder="Search strategies, pairs…" className="w-full md:w-64 pl-9 pr-9 min-h-11 bg-background"
        onFocus={() => setOpen(true)} onBlur={e => { if (!root.current?.contains(e.relatedTarget)) setOpen(false) }}
        onChange={e => { setSearchTerm(e.target.value); setActive(0); setError(''); setOpen(true) }}
        onKeyDown={e => {
          if (e.key === 'Escape') { e.preventDefault(); setOpen(false); input.current?.blur() }
          else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault(); setOpen(true)
            setActive(i => results.length ? (i + (e.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length : 0)
          } else if (e.key === 'Enter' && open && results[currentIndex]) { e.preventDefault(); void select(results[currentIndex]) }
        }} />
      {searchTerm && <button aria-label="Clear search" disabled={busy} onMouseDown={e => e.preventDefault()} onClick={() => { setSearchTerm(''); setActive(0); setError(''); input.current?.focus() }} className="absolute right-0 top-0 min-h-11 min-w-9 flex items-center justify-center rounded-lg focus-visible:ring-2 focus-visible:ring-ring"><X aria-hidden="true" className="h-4 w-4" /></button>}
      {open && <div className="absolute top-full right-0 mt-2 w-full md:w-96 max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-background shadow-xl overflow-hidden">
        <p className="px-3 py-2 text-xs text-muted-foreground">Your saved strategies, pair shortcuts and pages · Ctrl/⌘ K</p>
        <div id={listId} role="listbox" aria-label="Search results" aria-busy={busy} className="max-h-[min(24rem,60vh)] overflow-y-auto">
          {results.map((r, i) => <button id={`${listId}-${i}`} key={r.id} role="option" aria-selected={i === currentIndex} tabIndex={-1} disabled={busy}
            onMouseDown={e => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => void select(r)}
            className={cn('w-full min-h-14 text-left px-3 py-2 flex items-center justify-between gap-3', i === currentIndex ? 'bg-secondary' : 'hover:bg-secondary/50')}>
            <span className="min-w-0"><span className="block text-sm font-medium break-words">{r.label}</span><span className="block text-xs text-muted-foreground">{r.detail}</span></span>
            <ArrowUpRight aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>)}
        </div>
        {busy && <p role="status" className="p-3 text-sm">Opening saved algorithm…</p>}
        {strategies.loading && <p role="status" className="px-3 py-2 text-xs text-muted-foreground">Loading your strategies…</p>}
        {strategies.error && <p role="alert" className="px-3 py-2 text-xs text-destructive">Saved strategies unavailable. <button className="underline min-h-11" onClick={() => strategies.refetch()}>Retry</button></p>}
        {!results.length && !strategies.loading && <p role="status" className="p-3 text-sm text-muted-foreground">No matches. Try a strategy name, BTC, or Paper Trading.</p>}
        {error && <p role="alert" className="p-3 text-sm text-destructive">{error}</p>}
      </div>}
    </div>
  </div>
}
