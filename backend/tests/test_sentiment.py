from datetime import datetime, timedelta, timezone
import httpx
import pytest
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.sentiment.providers import NewsAPISentimentProvider
from app.sentiment.scoring import probabilities

pytestmark = pytest.mark.asyncio

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(get_settings(), 'sentiment_inference_mode', 'hosted')
    monkeypatch.setattr(get_settings(), 'newsapi_delay_hours', 0)
    monkeypatch.setattr(get_settings(), 'newsapi_api_key', 'news-test-secret')
    monkeypatch.setattr(get_settings(), 'hf_token', 'hf-test-secret')

def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

def article(title='Bitcoin rises', url='https://example.com/article', hours=1):
    return {'title': title, 'url': url, 'source': {'name': 'Example'}, 'description': 'Publisher excerpt',
        'publishedAt': (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()}

async def test_news_scoring_filters_and_cache(client, auth_headers, configured, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert 'secret' not in str(request.url)
        if request.url.host == 'newsapi.org':
            assert request.headers['X-Api-Key'] == 'news-test-secret'
            return httpx.Response(200, json={'status': 'ok', 'articles': [article(), article(),
                article('Old Bitcoin news', hours=25), article('Bad URL', url='javascript:alert(1)'),
                article('Bitcoin down', url='https://example.com/down')]})
        assert request.url.host == 'router.huggingface.co'
        assert request.headers['Authorization'] == 'Bearer hf-test-secret'
        return httpx.Response(200, json=[{'label': 'positive', 'score': .7},
            {'label': 'negative', 'score': .1}, {'label': 'neutral', 'score': .2}])
    transport(monkeypatch, handler)
    response = await client.get('/api/sentiment/BTC', headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data['articles']) == 2 and data['counts']['positive'] == 2
    assert data['score'] == pytest.approx(.6) and data['confidence'] == pytest.approx(.7)
    assert data['label'] == 'positive' and not data['cached']
    again = await client.get('/api/sentiment/BTC', headers=auth_headers)
    assert again.json()['cached'] and len(calls) == 3
    assert 'secret' not in response.text

async def test_empty_news_not_neutral(configured, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json={'status': 'ok', 'articles': []}))
    with pytest.raises(AppError) as exc:
        await NewsAPISentimentProvider().get_sentiment('BTC')
    assert exc.value.code == 'SENTIMENT_NO_RECENT_NEWS'

@pytest.mark.parametrize('failure', ['news', 'model'])
async def test_provider_failure_is_redacted(configured, monkeypatch, failure):
    def handler(request):
        if request.url.host == 'newsapi.org' and failure != 'news':
            return httpx.Response(200, json={'status': 'ok', 'articles': [article()]})
        return httpx.Response(429, json={'error': 'news-test-secret hf-test-secret'})
    transport(monkeypatch, handler)
    with pytest.raises(AppError) as exc:
        await NewsAPISentimentProvider().get_sentiment('BTC')
    assert 'secret' not in str(exc.value)

async def test_auth_symbols_and_status(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), 'sentiment_inference_mode', 'hosted')
    assert (await client.get('/api/sentiment/status')).status_code == 401
    assert (await client.get('/api/sentiment/SOL', headers=auth_headers)).status_code == 422
    monkeypatch.setattr(get_settings(), 'newsapi_api_key', None)
    monkeypatch.setattr(get_settings(), 'hf_token', None)
    status = (await client.get('/api/sentiment/status', headers=auth_headers)).json()
    assert not status['news_configured'] and not status['model_configured']
    assert not status['trading_integration_enabled']
    assert (await client.get('/api/sentiment/BTC', headers=auth_headers)).status_code == 503

@pytest.mark.parametrize('raw', [[], [{'label':'positive','score':1}],
    [{'label':'positive','score':float('nan')},{'label':'negative','score':0},{'label':'neutral','score':0}],
    [{'label':'positive','score':.9},{'label':'negative','score':.9},{'label':'neutral','score':.9}]])
async def test_invalid_model_output(raw):
    with pytest.raises(ValueError): probabilities(raw)

async def test_free_plan_delay_window(configured, monkeypatch):
    monkeypatch.setattr(get_settings(), 'newsapi_delay_hours', 24)
    def handler(request):
        if request.url.host == 'newsapi.org':
            cutoff = datetime.fromisoformat(request.url.params['to'])
            assert datetime.now(timezone.utc) - cutoff >= timedelta(hours=24)
            return httpx.Response(200, json={'status':'ok','articles':[
                article('Bitcoin recent', hours=1), article('Bitcoin delayed', hours=26),
                article('Bitcoin too old', hours=49)]})
        return httpx.Response(200, json=[{'label':'positive','score':.7},
            {'label':'negative','score':.1},{'label':'neutral','score':.2}])
    transport(monkeypatch, handler)
    result = await NewsAPISentimentProvider().get_sentiment('BTC')
    assert result.feed_delay_hours == 24
    assert [item['title'] for item in result.articles] == ['Bitcoin delayed']

async def test_local_scoring_runs_off_event_loop(monkeypatch):
    import threading
    from app.sentiment.local_model import LocalFinBERTScorer
    event_loop_thread = threading.get_ident()
    def fake_classify(texts):
        assert threading.get_ident() != event_loop_thread
        return [{'positive': .7, 'negative': .1, 'neutral': .2} for _ in texts]
    monkeypatch.setattr('app.sentiment.local_model.classify', fake_classify)
    assert (await LocalFinBERTScorer().score(['Headline']))[0]['positive'] == .7

async def test_local_provider_needs_no_hf_token(configured, monkeypatch):
    from app.sentiment.local_model import LocalFinBERTScorer
    monkeypatch.setattr(get_settings(), 'sentiment_inference_mode', 'local')
    monkeypatch.setattr(get_settings(), 'hf_token', None)
    async def local_score(self, texts):
        return [{'positive':.7,'negative':.1,'neutral':.2} for _ in texts]
    monkeypatch.setattr(LocalFinBERTScorer, 'score', local_score)
    def handler(request):
        assert request.url.host == 'newsapi.org'  # No hosted inference request.
        return httpx.Response(200, json={'status':'ok','articles':[article()]})
    transport(monkeypatch, handler)
    result = await NewsAPISentimentProvider().get_sentiment('BTC')
    assert result.inference_mode == 'local' and result.score == pytest.approx(.6)

async def test_local_cache_absence_has_actionable_error(monkeypatch):
    from app.sentiment.local_model import classify
    def missing(*args, **kwargs):
        raise OSError('cache missing')
    monkeypatch.setattr('app.sentiment.local_model.load_model', missing)
    with pytest.raises(AppError) as exc:
        classify(['Headline'])
    assert exc.value.code == 'SENTIMENT_LOCAL_MODEL_UNAVAILABLE'

async def test_local_status_uses_model_cache_not_token(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), 'sentiment_inference_mode', 'local')
    monkeypatch.setattr(get_settings(), 'hf_token', None)
    monkeypatch.setattr('app.api.routes.sentiment.local_model_ready', lambda: True)
    status = (await client.get('/api/sentiment/status', headers=auth_headers)).json()
    assert status['model_configured'] and status['inference_mode'] == 'local'
