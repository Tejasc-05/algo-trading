import { motion } from 'framer-motion'
import { Brain, ExternalLink, MessageCircle, Newspaper } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { cn } from '@/utils/cn'

function SentimentGauge({ value, label }: { value: number; label: string }) {
  const color = value >= 60 ? 'text-success' : value >= 40 ? 'text-warning' : 'text-destructive'

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

const sentimentBadge = {
  positive: 'success' as const,
  negative: 'destructive' as const,
  neutral: 'secondary' as const,
}

export function SentimentPage() {
  const { data, loading, error } = useApi(() => api.sentiment.get('BTC'))
  const sentimentData = { overall: data ? Math.round((data.score + 1) * 50) : 0,
    positive: 0, neutral: 0, negative: 0, trend: data?.label ?? 'Unavailable', aiConfidence: data ? Math.round(data.confidence * 100) : 0 }
  const newsItems: { id: string; title: string; summary: string; source: string; time: string; sentiment: keyof typeof sentimentBadge }[] = []
  const socialPosts: { id: string; author: string; handle: string; content: string; likes: number; time: string; sentiment: keyof typeof sentimentBadge }[] = []
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Sentiment Analysis</h2>
        <p className="text-sm text-muted-foreground">
          AI-powered market sentiment from news, social media, and on-chain data
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary" />
              Market Sentiment
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data ? <SentimentGauge value={sentimentData.overall} label={data.label} /> :
              <p role={error ? 'alert' : undefined} className="text-sm text-muted-foreground py-8">{loading ? 'Loading sentiment…' : error || 'No sentiment available'}</p>}
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">AI Confidence</CardTitle>
            <Badge variant="secondary">{sentimentData.trend.toUpperCase()}</Badge>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-6">
              <div className="flex-1">
                <div className="flex justify-between mb-2">
                  <span className="text-sm text-muted-foreground">Model Confidence</span>
                  <span className="text-2xl font-bold text-primary">{data ? `${sentimentData.aiConfidence}%` : '—'}</span>
                </div>
                {data && <Progress value={sentimentData.aiConfidence} className="h-3" />}
                <p className="text-xs text-muted-foreground mt-3">
                  Sentiment appears when a configured provider supplies a result.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Newspaper className="h-4 w-4" />
              News Feed
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">News feed is not configured.</p>
            {newsItems.map((item, i) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="p-4 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors cursor-pointer group"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <Badge variant={sentimentBadge[item.sentiment]} className="text-[10px] shrink-0">
                    {item.sentiment}
                  </Badge>
                  <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <h4 className="text-sm font-medium mb-1">{item.title}</h4>
                <p className="text-xs text-muted-foreground mb-2">{item.summary}</p>
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span>{item.source}</span>
                  <span>·</span>
                  <span>{item.time}</span>
                </div>
              </motion.div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <MessageCircle className="h-4 w-4" />
              Social Feed
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">Social feed is not configured.</p>
            {socialPosts.map((post, i) => (
              <motion.div
                key={post.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="p-4 rounded-lg bg-secondary/30"
              >
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className="text-sm font-medium">{post.author}</span>
                    <span className="text-xs text-muted-foreground ml-2">{post.handle}</span>
                  </div>
                  <Badge variant={sentimentBadge[post.sentiment]} className="text-[10px]">
                    {post.sentiment}
                  </Badge>
                </div>
                <p className="text-sm mb-2">{post.content}</p>
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                  <span>{post.likes.toLocaleString()} likes</span>
                  <span>·</span>
                  <span>{post.time}</span>
                </div>
              </motion.div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
