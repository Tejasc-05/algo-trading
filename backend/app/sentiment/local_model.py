"""Pinned CPU FinBERT. Runtime uses cached files only; no inference API calls."""
import asyncio
import threading
from app.core.exceptions import AppError
from app.sentiment.scoring import MODEL, probabilities

REVISION = '4556d13015211d73dccd3fdd39d39232506f3e43'
_lock = threading.Lock()
_tokenizer = None
_model = None


def load_model(download=False):
    global _tokenizer, _model
    if _model is not None:
        return _tokenizer, _model
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    torch.set_num_threads(2)
    options = dict(revision=REVISION, local_files_only=not download, token=False, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, **options)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL, use_safetensors=False, **options)
    model.to('cpu').eval()
    _tokenizer, _model = tokenizer, model
    return tokenizer, model


def local_model_ready():
    import importlib.util
    if any(importlib.util.find_spec(name) is None for name in ('torch', 'transformers')):
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
        return all(isinstance(try_to_load_from_cache(MODEL, name, revision=REVISION), str)
            for name in ('config.json', 'pytorch_model.bin', 'vocab.txt', 'tokenizer_config.json'))
    except (ImportError, OSError, ValueError):
        return False


def classify(texts):
    with _lock:
        try:
            import torch
            tokenizer, model = load_model()
            inputs = tokenizer([text[:1000] for text in texts], padding=True, truncation=True,
                max_length=512, return_tensors='pt')
            with torch.inference_mode():
                values = torch.softmax(model(**inputs).logits, dim=-1).tolist()
            return [probabilities([{'label':model.config.id2label[index], 'score':value}
                for index, value in enumerate(row)]) for row in values]
        except (ImportError, OSError, ValueError, RuntimeError, KeyError, TypeError):
            raise AppError('SENTIMENT_LOCAL_MODEL_UNAVAILABLE',
                'Local FinBERT is not ready. Install the local dependencies and download the pinned model cache.', 503) from None


class LocalFinBERTScorer:
    token = None
    async def score(self, texts):
        return await asyncio.to_thread(classify, texts)


if __name__ == '__main__':
    # Explicit operator command authorizes the one-time public model download.
    with _lock:
        load_model(download=True)
    print('Pinned FinBERT model downloaded and loaded on CPU.')
