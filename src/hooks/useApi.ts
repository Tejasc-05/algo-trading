import { useState, useEffect, useCallback, useRef } from 'react'

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const currentFetcher = useRef(fetcher)
  currentFetcher.current = fetcher
  const generation = useRef(0)
  const fetchData = useCallback(async () => {
    const request = ++generation.current
    setLoading(true); setError(null)
    try {
      const result = await currentFetcher.current()
      if (request === generation.current) setData(result)
    } catch (err) {
      if (request === generation.current) {
        setData(null)
        setError(err instanceof Error ? err.message : 'Unable to load data')
      }
    } finally {
      if (request === generation.current) setLoading(false)
    }
  }, deps)
  useEffect(() => {
    void fetchData()
    const refresh = () => { void fetchData() }
    window.addEventListener('algoflow:update', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      ++generation.current
      window.removeEventListener('algoflow:update', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [fetchData])
  return { data, loading, error, refetch: fetchData }
}
