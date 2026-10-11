"""Automatic sample diagnostics, not ground-truth labels or trading authorization.

Thresholds are transparent triage policies; they are not calibrated accuracy gates.
Checks inspect only the selected sample after provider filtering/deduplication.
"""
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

LABELS = {'positive', 'negative', 'neutral'}
MAX_AGE_HOURS = 24
MIN_FRESH_HEADLINES = 3
MIN_CONFIDENCE = .60
MIN_MARGIN = .15
RSS_HOSTS = {'Cointelegraph': 'cointelegraph.com', 'CoinDesk': 'coindesk.com'}


def canonical_url(value):
    parsed = urlparse(value)
    params = sorted((key, val) for key, val in parse_qsl(parsed.query) if not key.lower().startswith('utm_'))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), '', urlencode(params), ''))


def check_sample(result, now=None):
    now = now or datetime.now(timezone.utc)
    reasons = {item.id: [] for item in result.articles}
    seen_titles, seen_urls = {}, {}
    stale = duplicates = uncertain = invalid = relevance = provenance = 0
    fresh = 0
    asset = re.compile(r'\b(bitcoin|btc)\b' if result.symbol == 'BTC' else r'\b(ethereum|ether|eth)\b', re.I)
    for item in result.articles:
        flags = reasons[item.id]
        if item.published_at.tzinfo is None or item.published_at > now or now-item.published_at > timedelta(hours=MAX_AGE_HOURS):
            flags.append('Publication time is missing a timezone, in the future, or older than 24 hours.'); stale += 1
        else:
            fresh += 1
        title_key = ' '.join(re.findall(r'\w+', item.title.casefold()))
        url_key = canonical_url(item.url)
        previous = seen_titles.get(title_key) or seen_urls.get(url_key)
        if previous is not None:
            flags.append('Repeated title or article URL in the selected sample.'); duplicates += 1
            reasons[previous].append('Repeated title or article URL in the selected sample.')
        seen_titles[title_key] = item.id
        seen_urls[url_key] = item.id
        if not asset.search(item.title):
            flags.append('Selected asset is not explicitly mentioned in the headline.'); relevance += 1
        parsed = urlparse(item.url)
        host = (parsed.hostname or '').lower()
        expected = RSS_HOSTS.get(item.source)
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password or (result.provider == 'rss' and (not expected or not (host == expected or host.endswith('.'+expected)))):
            flags.append('Article link does not match the expected HTTPS publisher domain.'); provenance += 1
        values = item.probabilities
        valid = (set(values) == LABELS and all(math.isfinite(value) and 0 <= value <= 1 for value in values.values())
            and abs(sum(values.values())-1) <= .02)
        if valid:
            ordered = sorted(values.values(), reverse=True)
            valid = (item.label in values and values[item.label] == ordered[0]
                and abs(item.confidence-values[item.label]) <= .001
                and abs(item.score-(values['positive']-values['negative'])) <= .001)
        if not valid:
            flags.append('Model probabilities are missing, invalid or inconsistent with the score.'); invalid += 1
        elif ordered[0] < MIN_CONFIDENCE or ordered[0]-ordered[1] < MIN_MARGIN:
            flags.append('Model probability is below 60% or its top two labels are within 15 percentage points.'); uncertain += 1
    sources = len({item.source for item in result.articles})
    def check(key, failures, good, attention):
        return {'key': key, 'status': 'attention' if failures else 'pass', 'message': attention if failures else good}
    checks = [
        check('freshness', stale, 'All selected headlines are within 24 hours.', f'{stale} headlines have stale or invalid publication times.'),
        check('duplicates', duplicates, 'No repeated titles or URLs in the selected sample.', f'{duplicates} duplicate entries found in the selected sample.'),
        check('asset_relevance', relevance, 'Selected asset appears in each headline.', f'{relevance} headlines do not explicitly mention the selected asset.'),
        check('publisher_links', provenance, 'Article links match HTTPS publisher-domain checks.', f'{provenance} article links need provenance review.'),
        check('probabilities', invalid, 'Probability distributions and scores are consistent.', f'{invalid} distributions or scores are missing or invalid.'),
        check('uncertainty', uncertain, 'No scores triggered the uncertainty policy.', f'{uncertain} headlines have uncertain model scores.'),
        check('coverage', fresh < MIN_FRESH_HEADLINES or sources < 2, 'At least three fresh headlines and two publishers are represented.', f'{fresh} fresh headlines across {sources} publishers; coverage is limited.'),
        check('feed_warnings', bool(result.warnings), 'No provider warnings reported.', ' · '.join(result.warnings)),
        check('sample_age', result.as_of.tzinfo is None or result.as_of > now or now-result.as_of > timedelta(minutes=10), 'Sample was computed within ten minutes.', 'Sample computation time is stale or invalid.'),
    ]
    flagged = [{'id': item.id, 'title': item.title, 'url': item.url, 'reasons': list(dict.fromkeys(reasons[item.id]))}
        for item in result.articles if reasons[item.id]]
    return {'policy_version': '1', 'checked_at': now.isoformat(),
        'status': 'attention' if any(item['status']=='attention' for item in checks) else 'checks_passed',
        'headline_count': len(result.articles), 'fresh_headlines': fresh, 'publisher_count': sources,
        'flagged_headlines': flagged, 'checks': checks, 'model_accuracy': 'not_measured',
        'trading_integration_enabled': False,
        'interpretation': 'Automatic diagnostics only. Publisher links do not verify claims; model confidence does not establish accuracy or profitability.'}
