import { clearBrowserSession, getCsrfToken, setBrowserSession, redirectToLogin } from './session';
/** Same-origin cookie authentication with session-bound CSRF proof. */
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

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  if (options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method) && !getCsrfToken()
      && !['/auth/browser/login', '/auth/browser/register'].includes(path)) {
    // Recovery pages can be loaded directly in a tab with an existing cookie.
    // An expired cookie is cleared by this endpoint before public reset calls.
    const session = await fetch(`${API_BASE}/auth/browser/session`, { credentials: 'same-origin' });
    if (session.ok) {
      const result = await session.json(); setBrowserSession(result.user.id, result.csrf_token);
    } else if (session.status !== 401) {
      throw new ApiError('Unable to verify your session. Try again.', session.status, 'SESSION_UNAVAILABLE');
    }
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(getCsrfToken() ? { 'X-CSRF-Token': getCsrfToken() } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      redirectToLogin()
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
export interface NewsSummary {
  headline_count: number; publisher_count: number; score: number | null;
  label: 'positive' | 'negative' | 'neutral' | null; confidence: number | null;
  counts: Record<string, number>; probabilities: Record<string, number>
}
export interface NewsAggregation {
  method: string; reference_at?: string; fresh_window_hours: number; half_life_hours: number;
  fresh: NewsSummary; older: NewsSummary; deduplicated_headlines: number; deduplication_method: string
}
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
      request<{ csrf_token: string; user: any }>(
        '/auth/browser/register',
        {
          method: 'POST',
          body: JSON.stringify({ email, password, full_name: fullName }),
        }
      ).then(result => { setBrowserSession(result.user.id, result.csrf_token); return result }),
    login: (email: string, password: string, totp_code?: string) =>
      request<{ csrf_token: string; user: any }>('/auth/browser/login', {
        method: 'POST',
        body: JSON.stringify({ email, password, totp_code }),
      }).then(result => { setBrowserSession(result.user.id, result.csrf_token); return result }),
    session: () => request<{ csrf_token: string; user: any }>('/auth/browser/session')
      .then(result => { setBrowserSession(result.user.id, result.csrf_token); return result }),
    logout: () => request<void>('/auth/browser/logout', { method: 'POST' }).then(() => clearBrowserSession()),
    me: () => request<any>('/auth/me'),
    forgotPassword: (email: string) => request<{ message: string }>('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) }),
    resetPassword: (token: string, password: string, confirm_password: string) => request<{ message: string }>('/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, password, confirm_password }) }),
  },

  security: {
    status: () => request<{ email_verified: boolean; mfa_enabled: boolean; recent_mfa: boolean }>('/security/status'),
    requestEmail: () => request<{ message: string }>('/security/email/request', { method: 'POST' }),
    verifyEmail: (token: string) => request<{ message: string }>('/security/email/verify', { method: 'POST', body: JSON.stringify({ token }) }),
    enrollMfa: (password: string) => request<{ secret: string }>('/security/mfa/enroll', { method: 'POST', body: JSON.stringify({ password }) }),
    confirmMfa: (code: string) => request<{ message: string; csrf_token: string }>('/security/mfa/confirm', { method: 'POST', body: JSON.stringify({ code }) })
      .then(async result => { await api.auth.session(); return result }),
    stepUp: (password: string, code: string) => request<{ message: string }>('/security/step-up', { method: 'POST', body: JSON.stringify({ password, code }) }),
  },

  live: {
    readiness: () => request<{ ready: boolean; checks: { key: string; passed: boolean; message: string }[] }>('/live/readiness'),
    verify: (id: string) => request<{ message: string }>(`/live/connections/${id}/verify`, { method: 'POST' }),
    accounts: () => request<{ id: string; connection_id: string; verified_at: string | null }[]>('/live/accounts'),
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
      request<{ aggregation: Partial<NewsAggregation>; quality: SentimentQuality; symbol: string; score: number | null; label: 'positive' | 'negative' | 'neutral' | null; confidence: number | null; as_of: string; model: string; provider: string; warnings: string[]; inference_mode: 'local' | 'hosted'; cached: boolean; feed_delay_hours: number; window_hours: number; counts: Record<string, number>; articles: { id: string; title: string; summary: string; source: string; url: string; published_at: string; related_sources?: string[]; label: 'positive' | 'negative' | 'neutral' }[] }>(`/sentiment/${encodeURIComponent(symbol)}${provider ? `?provider=${encodeURIComponent(provider)}` : ''}`),
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
