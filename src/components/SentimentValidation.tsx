import { useState } from 'react'
import { api, type HeadlineReview, type HumanLabel, type SourceVerdict, type SentimentQuality } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

const labels = ['positive', 'negative', 'neutral']
const percentage = (value: number | null) => value === null ? '—' : `${(value * 100).toFixed(1)}%`

function ReviewRow({ item, onSaved }: { item: HeadlineReview; onSaved: () => Promise<void> }) {
  const [label, setLabel] = useState<HumanLabel | ''>(item.human_label || '')
  const [verdict, setVerdict] = useState<SourceVerdict>(item.source_verdict)
  const [notes, setNotes] = useState(item.notes)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  async function save() {
    setSaving(true); setMessage('')
    try {
      await api.sentiment.review(item.id, { human_label: label || null, source_verdict: verdict, notes })
      await onSaved(); setMessage('Review saved')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to save review') }
    finally { setSaving(false) }
  }
  return <div className="border border-border rounded-lg p-4 space-y-3">
    <a href={item.article.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium underline focus-visible:outline focus-visible:outline-primary">{item.article.title}<span className="sr-only"> (opens in new tab)</span></a>
    <p className="text-xs text-muted-foreground">{item.article.source} · Published {new Date(item.article.published_at).toLocaleString()} · First observed {new Date(item.first_seen_at).toLocaleString()}</p>
    <div className="grid sm:grid-cols-2 gap-3">
      <label className="text-sm" htmlFor={`label-${item.id}`}>Your headline label
        <select id={`label-${item.id}`} disabled={saving} value={label} onChange={event => setLabel(event.target.value as HumanLabel | '')} className="block mt-1 bg-secondary border border-border rounded-md p-2 min-h-11 w-full">
          <option value="">Not labeled</option><option value="positive">Positive</option><option value="negative">Negative</option><option value="neutral">Neutral</option><option value="ambiguous">Ambiguous / exclude</option>
        </select>
      </label>
      <label className="text-sm" htmlFor={`source-${item.id}`}>Source verification
        <select id={`source-${item.id}`} disabled={saving} value={verdict} onChange={event => setVerdict(event.target.value as SourceVerdict)} className="block mt-1 bg-secondary border border-border rounded-md p-2 min-h-11 w-full">
          <option value="unverified">Not checked</option><option value="verified">Verified article and claim</option><option value="questionable">Questionable / exclude</option>
        </select>
      </label>
    </div>
    <label className="block text-sm" htmlFor={`notes-${item.id}`}>Review notes / supporting source
      <textarea id={`notes-${item.id}`} maxLength={2000} disabled={saving} value={notes} onChange={event => setNotes(event.target.value)} className="block mt-1 w-full bg-secondary border border-border rounded-md p-2" rows={2} />
    </label>
    <div className="flex flex-wrap items-center gap-3"><Button onClick={() => void save()} disabled={saving}>{saving ? 'Saving…' : 'Save review'}</Button><span role="status" className="text-sm">{message}</span></div>
    {item.human_label && <p className="text-xs text-success">Saved label: {item.human_label} · Source: {item.source_verdict}</p>}
    <p className="text-xs text-muted-foreground">{item.article.label ? `Model: ${item.article.label} · ${percentage(item.article.confidence ?? null)} label probability` : 'Model prediction is hidden here until you save a label.'}</p>
  </div>
}

function ManualValidation({ symbol, revision }: { symbol: string; revision?: string }) {
  const [offset, setOffset] = useState(0)
  const reviews = useApi(() => api.sentiment.reviews(symbol, offset), [symbol, revision, offset])
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const report = reviews.data?.metrics
  async function download(format: 'json' | 'csv') {
    setExporting(true); setExportError('')
    try {
      const dataset = await api.sentiment.export(symbol)
      let next = dataset.next_offset
      while (next !== null) {
        const page = await api.sentiment.export(symbol, next)
        dataset.items.push(...page.items); next = page.next_offset
      }
      dataset.next_offset = null
      // Quoting alone does not prevent spreadsheet formula execution.
      const cell = (value: unknown) => {
        let text = value == null ? '' : String(value)
        if (/^[\s]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`
        return `"${text.replaceAll('"', '""')}"`
      }
      const fields = ['review_id', 'symbol', 'title', 'url', 'source', 'published_at', 'first_seen_at', 'model', 'model_revision', 'model_label', 'confidence', 'positive_probability', 'negative_probability', 'neutral_probability', 'human_label', 'source_verdict', 'notes']
      const csv = [fields.map(cell).join(','), ...dataset.items.map(item => [item.id, symbol, item.article.title, item.article.url, item.article.source, item.article.published_at, item.first_seen_at, item.article.model, item.article.model_revision, item.article.label, item.article.confidence, item.article.probabilities?.positive, item.article.probabilities?.negative, item.article.probabilities?.neutral, item.human_label, item.source_verdict, item.notes].map(cell).join(','))].join('\r\n')
      const url = URL.createObjectURL(new Blob([format === 'csv' ? csv : JSON.stringify(dataset, null, 2)], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json' }))
      const link = document.createElement('a'); link.href = url; link.download = `algoflow-${symbol.toLowerCase()}-sentiment-reviews.${format}`
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) { setExportError(error instanceof Error ? error.message : 'Export failed') }
    finally { setExporting(false) }
  }
  return <div className="space-y-6">
    <Card><CardHeader><CardTitle className="text-base">Headline Validation</CardTitle></CardHeader><CardContent className="space-y-4">
      <p className="text-sm text-muted-foreground">Label the financial wording, then verify the linked article and cross-check major claims against primary sources. Notes can record uncertainty, sponsorship or asset relevance. Reviews are private to your account. Aim for 100–200 varied headlines; repeated polling does not add copies.</p>
      <div className="flex flex-wrap gap-3"><Button disabled={exporting || !report?.total} onClick={() => void download('csv')}>{exporting ? 'Exporting…' : 'Export CSV'}</Button><Button variant="outline" disabled={exporting || !report?.total} onClick={() => void download('json')}>Export JSON</Button><Button variant="outline" onClick={() => void reviews.refetch()} disabled={reviews.loading}>Refresh reviews</Button></div>
      {exportError && <p role="alert" className="text-sm text-destructive">{exportError}</p>}
      {reviews.error && <p role="alert" className="text-sm text-destructive">{reviews.error}</p>}
      {report && <>
        <p className="text-sm">Collected: {report.total} · Labeled: {report.reviewed} · Evaluated: {report.evaluated} · Excluded: {report.excluded}</p>
        {report.evaluated < 100 && <p className="text-sm text-warning">Small review sample: these metrics are preliminary.</p>}
        <p className="text-sm">Agreement: {percentage(report.accuracy)} · Macro-F1: {percentage(report.macro_f1)}</p>
        <p className="text-xs text-muted-foreground">{report.interpretation} Only positive/negative/neutral labels with verified sources enter metrics. Missing classes contribute zero to macro-F1.</p>
        {report.evaluated > 0 && <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="text-left text-muted-foreground pb-2">Classification metrics and confusion matrix (rows: your label; columns: model prediction)</caption><thead><tr><th className="text-left p-2">Label</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th>{labels.map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{labels.map(label => <tr key={label}><th scope="row" className="text-left p-2">{label}</th><td className="text-center">{percentage(report.per_class[label].precision)}</td><td className="text-center">{percentage(report.per_class[label].recall)}</td><td className="text-center">{percentage(report.per_class[label].f1)}</td><td className="text-center">{report.per_class[label].support}</td>{labels.map(prediction => <td key={prediction} className="text-center">{report.confusion_matrix[label][prediction]}</td>)}</tr>)}</tbody></table></div>}
      </>}
      {reviews.loading && !reviews.data ? <p className="text-sm">Loading reviews…</p> : reviews.data?.items.length === 0 ? <p className="text-sm text-muted-foreground">No collected headlines for this asset. Refresh news to collect available evidence.</p> : reviews.data?.items.map(item => <ReviewRow key={`${item.id}:${item.human_label}:${item.source_verdict}:${item.notes}`} item={item} onSaved={reviews.refetch} />)}
      {report && report.total > 50 && <div className="flex items-center gap-3"><Button variant="outline" disabled={offset === 0 || reviews.loading} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button><span className="text-sm">Page {Math.floor(offset / 50) + 1}</span><Button variant="outline" disabled={offset + 50 >= report.total || reviews.loading} onClick={() => setOffset(offset + 50)}>Next</Button></div>}
    </CardContent></Card>
  </div>
}


export function SentimentValidation({ symbol, revision, quality }: { symbol: string; revision?: string; quality?: SentimentQuality }) {
  const health = useApi(() => api.sentiment.health(symbol), [symbol, revision])
  const [advanced, setAdvanced] = useState(false)
  return <div className="space-y-6">
    <Card><CardHeader><CardTitle className="text-base">Source Health</CardTitle></CardHeader><CardContent className="space-y-3">
      {health.loading && <p className="text-sm">Loading source health…</p>}
      {health.error && <p role="alert" className="text-sm text-destructive">{health.error}</p>}
      <p className="text-sm text-muted-foreground">{health.data?.message}</p>
      <div className="grid sm:grid-cols-2 gap-3">{health.data?.sources.map(source => <div key={source.source} className="rounded-lg border border-border p-3 space-y-1">
        <p className="text-sm font-medium">{source.source}: {source.status}</p>
        <p className="text-xs text-muted-foreground">Checked: {source.checked_at ? new Date(source.checked_at).toLocaleString() : 'Not yet checked'}</p>
        <p className="text-xs">{source.matching_headlines ?? '—'} matching headlines before deduplication</p>
        <p className="text-xs">Newest headline: {source.newest_published_at ? new Date(source.newest_published_at).toLocaleString() : 'None in the sample window'}</p>
        {source.newest_published_at && Date.now() - Date.parse(source.newest_published_at) > 24 * 60 * 60 * 1000 && <p className="text-xs text-warning">Newest matching headline is older than 24 hours.</p>}
        {source.checked_at && Date.now() - Date.parse(source.checked_at) > 10 * 60 * 1000 && <p className="text-xs text-warning">Health check is older than 10 minutes.</p>}
      </div>)}</div>
    </CardContent></Card>

    <Card><CardHeader><CardTitle className="text-base">Automatic Sentiment Checks</CardTitle></CardHeader><CardContent className="space-y-3">
      {quality ? <>
        <p role="status" className="text-sm font-medium">{quality.status === 'attention' ? 'Some checks need attention' : 'Sample checks passed'}</p>
        <p className="text-sm">{quality.headline_count} headlines · {quality.fresh_headlines} within 24 hours · {quality.publisher_count} publishers</p>
        <p className="text-xs text-muted-foreground">Checked {new Date(quality.checked_at).toLocaleString()}. Checks run automatically when sentiment loads or refreshes.</p>
        <ul className="space-y-2 text-sm">{quality.checks.map(check => <li key={check.key} className={check.status === 'attention' ? 'text-warning' : 'text-muted-foreground'}><span className="font-medium">{check.status === 'attention' ? 'Attention' : 'Pass'}:</span> {check.message}</li>)}</ul>
        {quality.flagged_headlines.length > 0 && <details className="border border-border rounded-lg p-3"><summary className="cursor-pointer min-h-11 flex items-center text-sm font-medium focus-visible:outline focus-visible:outline-primary">Flagged headlines ({quality.flagged_headlines.length})</summary><div className="space-y-3 pt-2">{quality.flagged_headlines.map(item => <div key={item.id} className="text-sm"><a className="underline" href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<span className="sr-only"> (opens in new tab)</span></a><ul className="list-disc pl-5 text-muted-foreground">{item.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div>)}</div></details>}
        <p className="text-sm text-muted-foreground">{quality.interpretation}</p>
      </> : <p className="text-sm text-muted-foreground">No current sample to check. Source health remains available above; refresh news to retry.</p>}
      <p className="text-sm text-muted-foreground">No manual labeling is required to use the dashboard. Crypto sentiment accuracy has not been measured, and trading integration remains disabled.</p>
    </CardContent></Card>
    <details onToggle={event => setAdvanced(event.currentTarget.open)} className="border border-border rounded-lg p-4">
      <summary className="cursor-pointer min-h-11 flex items-center text-sm font-medium focus-visible:outline focus-visible:outline-primary">Advanced: optional accuracy review and exports</summary>
      {advanced && <div className="pt-4"><ManualValidation symbol={symbol} revision={revision} /></div>}
    </details>
  </div>
}
