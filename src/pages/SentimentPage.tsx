import { SentimentValidation } from '@/components/SentimentValidation'
import { useState } from 'react'
import { Brain, ExternalLink, MessageCircle, Newspaper } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { cn } from '@/utils/cn'

function SentimentGauge({ value, label }: { value: number; label: string }) {
  const color = label === 'positive' ? 'text-success' : label === 'negative' ? 'text-destructive' : 'text-warning'

  return (
    <div className="text-center">
      <div className="relative mx-auto w-32 h-32 mb-3">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="42" fill="none" stroke="currentColor" strokeWidth="8" className="text-secondary" />
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            strokeDasharray={`${value * 2.64} 264`}
            strokeLinecap="round"
            className={color}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn('text-3xl font-bold', color)}>{value}</span>
          <span className="text-[10px] text-muted-foreground uppercase">{label}</span>
        </div>
      </div>
    </div>
  )
}

const sentimentBadge = { positive: 'success', negative: 'destructive', neutral: 'secondary' } as const

export function SentimentPage() {
  const [symbol, setSymbol] = useState('BTC')
  const { data, loading, error, refetch } = useApi(() => api.sentiment.get(symbol), [symbol])
  const { data: setup } = useApi(() => api.sentiment.status())
  const configured = setup?.news_configured && setup?.model_configured
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Sentiment Analysis</h2>
          <p className="text-sm text-muted-foreground">Financial news headlines scored by FinBERT. Analysis only; no trading orders.</p>
        </div>
        <div className="flex items-end gap-3">
          <label className="text-sm">Asset
            <select aria-label="Sentiment asset" className="block bg-secondary border border-border rounded-md p-2 mt-1 min-h-11" value={symbol} onChange={event => setSymbol(event.target.value)}>
              <option value="BTC">Bitcoin (BTC)</option><option value="ETH">Ethereum (ETH)</option>
            </select>
          </label>
          <Button onClick={() => void refetch()} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</Button>
        </div>
      </div>
      {setup && !configured && <Card><CardContent className="pt-6 text-sm space-y-2">
        <p className="font-medium">News sentiment needs setup</p>
        <p className="text-muted-foreground">Configure the news source and prepare FinBERT on the server (local model or hosted inference token). Never enter exchange API keys here.</p>
        <p>{setup.provider === 'rss' ? 'Publisher RSS' : 'NewsAPI'}: {setup.news_configured ? 'Configured' : 'Not configured'} · FinBERT model: {setup.model_configured ? 'Configured' : 'Not configured'}</p>
      </CardContent></Card>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {data?.warnings?.map(warning => <p key={warning} role="status" className="text-sm text-warning">{warning}; results use the available feed.</p>)}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6" aria-busy={loading}>
        <Card><CardHeader><CardTitle className="text-base flex items-center gap-2"><Brain aria-hidden="true" className="h-4 w-4 text-primary" />Market Sentiment</CardTitle></CardHeader>
          <CardContent>{data && !loading ? <><SentimentGauge value={Math.round((data.score + 1) * 50)} label={data.label} /><p className="text-xs text-muted-foreground text-center">0 = negative · 50 = balanced · 100 = positive</p></> : <p className="text-sm text-muted-foreground py-8">{loading ? 'Loading sentiment…' : 'No sentiment score available'}</p>}</CardContent>
        </Card>
        <Card className="md:col-span-2"><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base">Headline Classification</CardTitle><Badge variant="secondary">{data && !loading ? data.label.toUpperCase() : 'UNAVAILABLE'}</Badge></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-muted-foreground">Aggregate label probability</span><span className="text-2xl font-bold text-primary">{data && !loading ? `${Math.round(data.confidence * 100)}%` : '—'}</span></div>
            {data && !loading && <><Progress value={data.confidence * 100} className="h-3" /><p className="text-sm">{data.articles.length} headlines · Positive: {data.counts.positive} · Neutral: {data.counts.neutral} · Negative: {data.counts.negative}</p>
              <p className="text-xs text-muted-foreground">{data.provider === 'rss' ? 'Publisher RSS' : 'NewsAPI'} · {data.model} ({data.inference_mode}) · {data.window_hours}-hour sample · Feed delay: {data.feed_delay_hours}h · Computed {new Date(data.as_of).toLocaleString()}{data.cached ? ' · Cached (up to 5 minutes)' : ''}</p></>}
            <p className="text-sm text-muted-foreground">Model probabilities describe headline wording, not the chance of a price move or a profitable trade. FinBERT is a financial-text model; crypto-specific accuracy has not been validated.</p>
          </CardContent>
        </Card>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card><CardHeader><CardTitle className="text-base flex items-center gap-2"><Newspaper aria-hidden="true" className="h-4 w-4" />News Feed</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {(!data || loading) && <p className="text-sm text-muted-foreground">{loading ? 'Loading news…' : 'No news evidence available. Configure the source or retry.'}</p>}
            {!loading && data?.articles.map(item => <a key={item.id} href={item.url} target="_blank" rel="noopener noreferrer" className="block p-4 rounded-lg bg-secondary/30 hover:bg-secondary/50 focus-visible:outline focus-visible:outline-primary transition-colors">
              <div className="flex justify-between gap-2 mb-2"><Badge variant={sentimentBadge[item.label]}>{item.label}</Badge><ExternalLink aria-hidden="true" className="h-4 w-4 text-muted-foreground" /></div>
              <h4 className="text-sm font-medium mb-1">{item.title}<span className="sr-only"> (opens in new tab)</span></h4>
              {item.summary && <p className="text-sm text-muted-foreground mb-2">{item.summary}</p>}
              <p className="text-xs text-muted-foreground">{item.source} · {new Date(item.published_at).toLocaleString()}</p>
            </a>)}
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-base flex items-center gap-2"><MessageCircle aria-hidden="true" className="h-4 w-4" />Social Feed</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">Social sources are not integrated yet. News sentiment excludes social posts and on-chain data.</p></CardContent></Card>
      </div>
      <SentimentValidation key={symbol} symbol={symbol} quality={loading ? undefined : data?.quality} revision={`${data?.as_of}:${loading}:${error}`} />
    </div>
  )
}
