"""Conservative story selection and explicit recency-weighted headline summaries."""
import re
from math import exp, log
from app.sentiment.quality import canonical_url

POLICY = 'recency-v1'
FRESH_HOURS = 24
HALF_LIFE_HOURS = 12
LABELS = ('positive', 'negative', 'neutral')
STOP_WORDS = {'a', 'an', 'the', 'of', 'to', 'in', 'on', 'at', 'for', 'with', 'and', 'as', 'by'}
DIRECTION = {'no', 'not', 'never', 'denies', 'denied', 'rejects', 'rejected', 'approves', 'approved', 'rises', 'falls', 'buy', 'sell', 'long', 'short', 'inflows', 'outflows', 'increase', 'decrease', 'increases', 'decreases', 'surges', 'drops', 'approval', 'rejection', 'bullish', 'bearish', 'gains', 'losses', 'up', 'down', 'raises', 'cuts', 'halts', 'resumes'}


def tokens(title):
    words = re.findall(r'[a-z0-9]+', title.casefold())
    aliases = {'btc':'bitcoin', 'eth':'ethereum', 'ether':'ethereum'}
    return [aliases.get(word, word) for word in words if word not in STOP_WORDS]


def same_story(left, right):
    if canonical_url(left['url']) == canonical_url(right['url']):
        return True
    a, b = tokens(left['title']), tokens(right['title'])
    if a == b: return True
    # Similarity is deliberately strict and restricted to nearby publisher
    # reports. Different numbers/negations must never collapse opposing news.
    if left['source'] == right['source'] or abs((left['published_at'] - right['published_at']).total_seconds()) > 12 * 3600:
        return False
    a, b = set(a), set(b)
    if {w for w in a if any(c.isdigit() for c in w)} != {w for w in b if any(c.isdigit() for c in w)}:
        return False
    if (a & DIRECTION) != (b & DIRECTION): return False
    overlap = len(a & b)
    return overlap >= 6 and overlap / len(a | b) >= .8


def select_stories(articles, limit=30):
    selected = []
    removed = 0
    # Keep newest representative, so duplicates cannot increase sentiment weight.
    for raw in sorted(articles, key=lambda item:item['published_at'], reverse=True):
        item = dict(raw)
        duplicate = next((previous for previous in selected if same_story(previous, item)), None)
        if duplicate is not None:
            removed += 1
            duplicate['related_sources'] = sorted(set(duplicate['related_sources']) | {item['source']})
        else:
            item['related_sources'] = [item['source']]
            selected.append(item)
    return selected[:limit], removed


def summarize(articles, now):
    counts = dict.fromkeys(LABELS, 0)
    for item in articles: counts[item['label']] += 1
    if not articles:
        return {'headline_count':0, 'publisher_count':0, 'counts':counts,
            'score':None, 'label':None, 'confidence':None, 'probabilities':{}}
    weights = [exp(-log(2) * max(0, (now - item['published_at']).total_seconds() / 3600) / HALF_LIFE_HOURS) for item in articles]
    total = sum(weights)
    aggregate = {label:sum(item['probabilities'][label] * weight for item,weight in zip(articles,weights,strict=True))/total for label in LABELS}
    label = max(aggregate, key=aggregate.get)
    return {'headline_count':len(articles), 'publisher_count':len({item['source'] for item in articles}),
        'counts':counts, 'score':aggregate['positive'] - aggregate['negative'],
        'label':label, 'confidence':aggregate[label], 'probabilities':aggregate}


def aggregate_news(articles, now, removed):
    fresh = [item for item in articles if 0 <= (now-item['published_at']).total_seconds() <= FRESH_HOURS*3600]
    older = [item for item in articles if (now-item['published_at']).total_seconds() > FRESH_HOURS*3600]
    return {'method':POLICY, 'reference_at':now.isoformat(), 'fresh_window_hours':FRESH_HOURS, 'half_life_hours':HALF_LIFE_HOURS,
        'fresh':summarize(fresh, now), 'older':summarize(older, now),
        'deduplicated_headlines':removed,
        'deduplication_method':'Canonical URLs, normalized titles and conservative cross-publisher similarity'}
