/** Centralized API client for AlgoFlow backend.
 *  All calls include auth header automatically.
 */
const API_BASE = import.meta.env.VITE_API_BASE || '/api';

class ApiError extends Error {
  status: number;
  code: string;

  constructor(
    message: string,
    status: number,
    code: string
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
      ...options.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      localStorage.removeItem('access_token'); localStorage.removeItem('user')
      window.location.assign('/login')
    }
    let message = 'Request failed';
    let code = 'REQUEST_FAILED';
    try {
      const err = await response.json();
      message = err.error?.message || (typeof err.detail === 'string' ? err.detail :
        Array.isArray(err.detail) ? err.detail.map((issue: { msg: string }) => issue.msg).join('; ') : message);
      code = err.error?.code || code;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(message, response.status, code);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export type HumanLabel = 'positive' | 'negative' | 'neutral' | 'ambiguous'
export type SourceVerdict = 'unverified' | 'verified' | 'questionable'
export interface HeadlineReview {
  id: string; first_seen_at: string; human_label: HumanLabel | null; source_verdict: SourceVerdict; notes: string
  article: { title: string; url: string; source: string; published_at: string; model: string; model_revision: string;
    label?: string; confidence?: number; probabilities?: Record<string, number> }
}
export interface ValidationMetrics {
  total: number; reviewed: number; evaluated: number; excluded: number; accuracy: number | null; macro_f1: number | null
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>
  confusion_matrix: Record<string, Record<string, number>>; interpretation: string
}
export interface ReviewExport { schema_version: number; symbol: string; metrics: ValidationMetrics; items: HeadlineReview[]; next_offset: number | null }
export interface SentimentQuality {
  checked_at: string; status: 'attention' | 'checks_passed'; headline_count: number; fresh_headlines: number; publisher_count: number
  checks: { key: string; status: 'pass' | 'attention'; message: string }[]
  flagged_headlines: { id: string; title: string; url: string; reasons: string[] }[]
  model_accuracy: string; trading_integration_enabled: boolean; interpretation: string
}
export interface SourceHealth { source: string; feed_url: string; status: string; checked_at: string | null;
  matching_headlines: number | null; newest_published_at: string | null }

export interface DiagnosticValue { current: number | boolean | null; previous: number | boolean | null }
export interface DemoNodeDiagnostic extends Partial<DiagnosticValue> {
  id: string; label: string; node_type: string; category: string; params: Record<string, string | number | null>
  inputs: DiagnosticValue[]; triggered?: boolean; macd?: Record<string, DiagnosticValue>
}
export interface DemoDiagnostics {
  checked_at: string; reason_code: string; reason: string
  position?: { side: string; quantity: string }
  last_error?: { code: string; message: string; at?: string } | null
  entry_limits?: { rounded_quantity: string; mark_price: string; notional: string; exchange_minimum_notional: string; maximum_notional: string; available_margin: string; checks: { label: string; passed: boolean }[] } | null
  evaluation?: {
    evaluated_at: string; candle_open_at: string; candle_close_at: string; next_candle_close_at: string
    strategy_version_id: string; strategy_version_number: number; bars_used: number; close_price: number | null
    nodes: DemoNodeDiagnostic[]; entry_signals: string[]; exit_signals: string[]; decision: string
  }
}
export interface DemoSessionView {
  id: string; symbol: string; timeframe: string; status: string; message: string
  connection_id: string; strategy_version_id: string; max_notional: number; loss_limit: number
  last_bar: string | null; diagnostics: DemoDiagnostics | null
}

export const api = {
  futuresDemo: {
    verify: (id: string) => request<any>(`/futures-demo/connections/${id}/verify`, { method: 'POST' }),
    list: () => request<DemoSessionView[]>('/futures-demo/sessions'),
    activate: (payload: { connection_id: string; strategy_id: string; symbol: string; timeframe: string; max_notional: number; loss_limit: number; confirm_demo: true }) =>
      request<DemoSessionView>('/futures-demo/sessions', { method: 'POST', body: JSON.stringify(payload) }),
    tick: (id: string) => request<DemoSessionView>(`/futures-demo/sessions/${id}/tick`, { method: 'POST' }),
    stop: (id: string) => request<DemoSessionView>(`/futures-demo/sessions/${id}/stop`, { method: 'POST' }),
    resume: (id: string) => request<DemoSessionView>(`/futures-demo/sessions/${id}/resume`, { method: 'POST' }),
    orders: (id: string) => request<any[]>(`/futures-demo/sessions/${id}/orders`),
  },
  // Auth
  auth: {
    register: (email: string, password: string, fullName?: string) =>
      request<{ access_token: string; user: any }>(
        '/auth/register',
        {
          method: 'POST',
          body: JSON.stringify({ email, password, full_name: fullName }),
        }
      ),
    login: (email: string, password: string) =>
      request<{ access_token: string; user: any }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    me: () => request<any>('/auth/me'),
  },

  // Strategies
  strategies: {
    validateGraph: (graph: unknown) => request<any>('/strategies/validate-graph', {
      method: 'POST', body: JSON.stringify(graph),
    }),
    list: () => request<any[]>('/strategies'),
    get: (id: string) => request<any>(`/strategies/${id}`),
    create: (payload: { name: string; description?: string; graph: any }) =>
      request<any>('/strategies', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    update: (id: string, payload: { name?: string; description?: string; graph: any }) =>
      request<any>(`/strategies/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    delete: (id: string) => request<void>(`/strategies/${id}`, { method: 'DELETE' }),
    validate: (id: string, graph?: any) =>
      request<any>(`/strategies/${id}/validate`, {
        method: 'POST',
        body: JSON.stringify({ graph }),
      }),
    execute: (id: string) =>
      request<any>(`/strategies/${id}/execute`, { method: 'POST' }),
  },

  // Market Data
  market: {
    ticker: (symbol: string) => request<any>(`/market/ticker?symbol=${encodeURIComponent(symbol)}`),
    ohlcv: (symbol: string, timeframe = '1h', limit = 100) =>
      request<any>(`/market/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`),
  },

  // Sentiment
  sentiment: {
    health: (symbol: string) => request<{ sources: SourceHealth[]; message: string }>(`/sentiment/health/${encodeURIComponent(symbol)}`),
    reviews: (symbol: string, offset = 0) => request<{ items: HeadlineReview[]; metrics: ValidationMetrics }>(`/sentiment/reviews/${encodeURIComponent(symbol)}?offset=${offset}`),
    review: (id: string, body: { human_label: HumanLabel | null; source_verdict: SourceVerdict; notes: string }) => request<HeadlineReview>(`/sentiment/reviews/item/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    export: (symbol: string, offset = 0) => request<ReviewExport>(`/sentiment/export/${encodeURIComponent(symbol)}?offset=${offset}`),
    status: () => request<{ provider: string; news_configured: boolean; model_configured: boolean }>('/sentiment/status'),
    get: (symbol: string, provider?: string) =>
      request<{ quality: SentimentQuality; symbol: string; score: number; label: 'positive' | 'negative' | 'neutral'; confidence: number; as_of: string; model: string; provider: string; warnings: string[]; inference_mode: 'local' | 'hosted'; cached: boolean; feed_delay_hours: number; window_hours: number; counts: Record<string, number>; articles: { id: string; title: string; summary: string; source: string; url: string; published_at: string; label: 'positive' | 'negative' | 'neutral' }[] }>(`/sentiment/${encodeURIComponent(symbol)}${provider ? `?provider=${encodeURIComponent(provider)}` : ''}`),
  },

  // Backtesting
  backtest: {
    run: (payload: {
      strategy_id: string;
      strategy_version?: number;
      symbol: string;
      timeframe: string;
      start_date: string;
      end_date: string;
      starting_capital: number;
      fees_pct: number;
      slippage_pct: number;
      engine: 'vectorbt' | 'backtrader';
    }) => request<any>('/backtest', { method: 'POST', body: JSON.stringify(payload) }),
    get: (id: string) => request<any>(`/backtest/${id}`),
  },

  // Paper Trading
  paperTrading: {
    getUsage: () => request<{ active_bots: number }>('/paper-trading/usage'),
    start: (payload: { strategy_id: string; symbol: string; timeframe?: string; starting_balance?: number; market_type?: 'spot' | 'futures'; leverage?: number; fee_rate?: number; slippage_rate?: number; funding_rate?: number; maintenance_margin_rate?: number }) =>
      request<any>('/paper-trading/start', { method: 'POST', body: JSON.stringify(payload) }),
    stop: (paper_account_id: string, close_positions = false) => request<any>('/paper-trading/stop', { method: 'POST', body: JSON.stringify({ paper_account_id, close_positions }) }),
    resume: (paper_account_id: string) => request<any>('/paper-trading/resume', { method: 'POST', body: JSON.stringify({ paper_account_id }) }),
    tick: (paper_account_id: string) => request<any>('/paper-trading/tick', { method: 'POST', body: JSON.stringify({ paper_account_id }) }),
    accounts: () => request<any[]>('/paper-trading/accounts'),
    positions: (id: string) => request<any[]>(`/paper-trading/positions?paper_account_id=${encodeURIComponent(id)}`),
    performance: (id: string) => request<any>(`/paper-trading/performance?paper_account_id=${encodeURIComponent(id)}`),
    getAccount: (id?: string) => request<any>(`/paper-trading/account${id ? `?paper_account_id=${encodeURIComponent(id)}` : ''}`),
    getTrades: (id?: string) => request<any[]>(`/paper-trading/trades${id ? `?paper_account_id=${encodeURIComponent(id)}` : ''}`),
    createOrder: (payload: { paper_account_id: string; symbol: string; side: string; order_type: string; quantity: number; price?: number }) =>
      request<any>('/paper-trading/orders', { method: 'POST', body: JSON.stringify(payload) }),
    simulateFill: (order_id: string, current_price: number) =>
      request<any>('/paper-trading/simulate-fill', { method: 'POST', body: JSON.stringify({ order_id, current_price }) }),
  },

  // Exchanges
  exchanges: {
    connect: (payload: { exchange_name: string; label?: string; api_key: string; api_secret: string; passphrase?: string; is_testnet?: boolean }) =>
      request<any>('/exchanges/connect', { method: 'POST', body: JSON.stringify(payload) }),
    list: () => request<any[]>('/exchanges'),
    disconnect: (id: string) => request<void>(`/exchanges/${id}`, { method: 'DELETE' }),
    test: (id: string) => request<any>(`/exchanges/${id}/test`, { method: 'POST' }),
  },

  // Portfolio
  portfolio: {
    get: () => request<any>('/portfolio'),
    performance: () => request<any>('/portfolio/performance'),
  },

  // Errors
  ApiError,
};

export type { ApiError };
