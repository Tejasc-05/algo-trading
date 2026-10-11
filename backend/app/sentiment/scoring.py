"""FinBERT headline inference. No invented or lexical fallback scores."""
import math
import asyncio
import httpx
from app.core.exceptions import AppError

MODEL = 'ProsusAI/finbert'
URL = 'https://router.huggingface.co/hf-inference/models/' + MODEL
LABELS = {'positive', 'negative', 'neutral'}


def probabilities(raw):
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
        raw = raw[0]
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError('Invalid classification shape')
    values = {str(item['label']).lower(): float(item['score']) for item in raw}
    if set(values) != LABELS or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values.values()):
        raise ValueError('Invalid classification probabilities')
    if abs(sum(values.values()) - 1) > 0.01:
        raise ValueError('Invalid probability sum')
    return values


class FinBERTScorer:
    def __init__(self, token):
        self.token = token

    async def score(self, texts):
        if not self.token:
            raise AppError('SENTIMENT_UNAVAILABLE', 'Configure the backend HF_TOKEN for FinBERT inference.', 503)
        semaphore = asyncio.Semaphore(3)
        # Bounded headline requests avoid assuming a provider-specific batch contract.
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async def classify(text):
                async with semaphore:
                    try:
                        response = await client.post(URL, headers={'Authorization': 'Bearer ' + self.token},
                            json={'inputs': text[:1000], 'parameters': {'top_k': 3}})
                        response.raise_for_status()
                        return probabilities(response.json())
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        raise AppError('SENTIMENT_MODEL_UNAVAILABLE',
                            'FinBERT inference failed. Check token permissions, model availability and inference quota.', 503) from None
            results = await asyncio.gather(*(classify(text) for text in texts), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            return results
