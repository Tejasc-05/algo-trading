# News sentiment

The existing sentiment dashboard defaults to public Cointelegraph/CoinDesk/Decrypt RSS headlines, with optional NewsAPI English BTC/ETH headlines scored by ProsusAI/finbert locally on CPU by default (hosted HF Inference is optional). CryptoPanic, X/social and on-chain sources remain unavailable. This service does not change, restart or feed orders to futures demo sessions. Sentiment strategy execution remains disabled pending a separate integration and acceptance tests.

## Key-free RSS setup (default)

No CryptoPanic, NewsAPI or Hugging Face inference token is needed for public RSS + local FinBERT. Configure SENTIMENT_NEWS_PROVIDER=rss and SENTIMENT_INFERENCE_MODE=local. Model dependencies/cache still need the local setup below. Publisher feeds are polled on demand, cached for five minutes and filtered by BTC/ETH words in titles. RSS_NEWS_WINDOW_HOURS defaults to 72 (range 24–168); the window is displayed. Future/missing/older publication times are rejected. No imposed provider delay is configured, but publication and feed delays can still occur. There is no promise of immediate breaking-news coverage.

Fixed publisher URLs are fetched with bounded response size, without redirects or credentials. Only UTF-8 RSS is parsed; DTD/entity declarations are rejected. Titles are scored and linked to the source; full article bodies and publisher HTML summaries are not scraped or republished. Duplicate titles are removed. Failed feeds produce visible partial-coverage warnings; all failed feeds or zero matching headlines produce an unavailable result, never a neutral guess. Public feed availability does not establish permission for unrestricted commercial redistribution; review publisher terms before release.

Historical acceptance: the initial development run used only Cointelegraph because CoinDesk’s former trailing-slash URL redirected. The canonical CoinDesk feed now omits that slash; Decrypt is also allowlisted. Source health retains checks for all three publishers; a changed URL is marked unknown until a fresh check.

## Optional NewsAPI setup

Create a NewsAPI key. Local inference does not need HF_TOKEN or hosted inference credits. Check the chosen providers' access, quota and plan terms; NewsAPI developer plans can return delayed news and have development-only restrictions. Configure only backend/.env:

```dotenv
NEWSAPI_API_KEY=your-news-key
SENTIMENT_INFERENCE_MODE=local
NEWSAPI_DELAY_HOURS=24
```

Never commit these values or use frontend environment variables. Build the API with local dependencies, recreate only the API, then download the public model once into the persistent finbert_cache volume:

```sh
cd backend
docker compose build api
docker compose up -d --no-deps --force-recreate api
docker compose exec -T api python -m app.sentiment.local_model
```

Open Sentiment Analysis, choose BTC or ETH, and click Refresh. Configured means a key exists, not that credentials or quota have been verified. Genuine news credentials are required for end-to-end news acceptance. Local model inference is checked separately using downloaded weights; news collection tests use injected responses. For local Python without Docker, install torch==2.13.0 and requirements-sentiment.txt, then run python -m app.sentiment.local_model. To use hosted inference instead, set SENTIMENT_INFERENCE_MODE=hosted and HF_TOKEN; hosted inference requires provider quota/credits.

## Meaning and provenance

GET /api/sentiment/status returns configuration booleans, supported assets, model name and trading-integration state. GET /api/sentiment/{BTC|ETH}?provider=newsapi requires JWT authentication. No private keys or user data enter its Redis cache.

Fetch at most 20 newest English titles mentioning Bitcoin or Ethereum from a 24-hour window ending NEWSAPI_DELAY_HOURS ago (default: 24, matching the free developer plan), drop duplicates/invalid URLs/missing or stale timestamps, and classify up to 10 unique headlines. Headline relevance is name-based, not entity disambiguation. Descriptions are displayed publisher excerpts, not AI summaries; only the headline is scored. Set NEWSAPI_DELAY_HOURS=0 only for a plan with real-time access. The dashboard explicitly labels the feed delay; delayed news is not current market sentiment. Linked articles are not fetched.

Each headline has positive/negative/neutral probabilities. NewsAPI retains an unweighted mean across its intentionally delayed sample. RSS uses `recency-v1`: classify up to 30 distinct stories, then separately summarize fresh (within 24 hours) and older (24 hours to the configured window) news. A headline’s weight is `2 ** (-age_hours / 12)`, normalized within each group. RSS top-level score, label, confidence, counts and probabilities describe only the fresh group. Older news has a separate context summary and never affects that score. With no fresh headlines, score/label/confidence are null and probabilities empty; older evidence remains visible. If no matching evidence exists anywhere in the configured window, return an error. The aggregate label is the largest weighted probability; score is weighted positive minus weighted negative, in [-1,1]. The gauge maps this to [0,100]. Confidence is the aggregate label probability, not a calibrated trading confidence or prediction accuracy. Counts classify each headline by its highest probability. A neutral label can accompany a small nonzero score.

Responses carry computation time, article publication time, source links, model, sample size and cache status. Public news results cache for 300 seconds with credential fingerprint invalidation. Refresh can return the same cached evidence. Local per-asset locks coalesce requests within one API process; multiple processes can make concurrent upstream calls. Hosted FinBERT inference concurrency is limited to three, with a 45-second overall provider timeout.

No matching evidence, quota/auth errors, invalid model output or timeouts produce errors, never a fabricated neutral score. Older-only RSS evidence returns a null recent score and an explicit warning rather than masquerading as current sentiment. Redis outages bypass cache. Scores are not saved as historical backtest inputs; no point-in-time replay is provided. FinBERT's financial-text training does not establish crypto-specific accuracy or strategy profitability. Provider availability can change; there is no silent fallback.

## Checks

Tests cover authentication, asset validation, missing keys, duplicate/stale/unsafe article removal, aggregation, caching, redacted failures and malformed inference probabilities. Browser checks cover setup/unavailable states and controlled scored-news responses.

References: [NewsAPI everything endpoint](https://newsapi.org/docs/endpoints/everything), [NewsAPI pricing and restrictions](https://newsapi.org/pricing), [FinBERT model card](https://huggingface.co/ProsusAI/finbert), [HF Inference](https://huggingface.co/docs/inference-providers/providers/hf-inference).

## Local execution

Pinned model revision: 4556d13015211d73dccd3fdd39d39232506f3e43. CPU float32, evaluation/inference mode, original tokenizer with truncation to 512 tokens, identical three-label softmax mapping. No quantization or retraining. Local calls run outside the async event loop; a process-wide lock serializes model loading/inference and CPU work uses two PyTorch threads. The loaded model is reused, and cached files persist across API recreation. Runtime uses local_files_only=True and token=False; it never falls back to paid hosted inference. Only the explicit download command accesses the public model repository.

For matching weights and preprocessing, local versus hosted scores should agree apart from floating-point differences; hosted preprocessing/revision cannot be verified here. This does not increase sentiment accuracy. CPU throughput and cold startup depend on hardware. Removing the finbert_cache Docker volume removes model files and requires downloading again. Local inference still consumes RAM/CPU and news retrieval still needs a news source.

Local acceptance on the development machine: three example headlines classified positive/negative/neutral with repeatable probabilities. Cold model load plus three headlines took 5.501 seconds; warm three-headline CPU inference took 0.216 seconds in one measured run. These are small-sample measurements, not throughput guarantees or a hosted/local equivalence benchmark. All 118 backend tests passed; all 14 sentiment tests also passed inside the CPU-enabled API container. The full test suite runs from the host repository because template tests depend on frontend JSON files outside the backend-only container mount.

## Source health and validation workflow

Migration `0006_sentiment_validation` adds immutable public headline evidence and
private, user-owned review rows. Successful sentiment reads capture evidence for
that user, including cache hits; unchanged URL/title/asset/provider/model revision
and inference mode do not create duplicate reviews. The observation timestamp is
when this installation first persisted the evidence, **not** its publication time.
Older cached news cannot be treated as historically available trading signals.
Evidence preserves the exact title, original URL, publisher, publication time,
model revision, inference mode, computation time and individual probabilities.
Hosted inference has an explicitly unknown/unpinned revision.

On **Sentiment Analysis**, use **Source Health** to inspect RSS feed reachability,
last check, matching headline counts before deduplication and newest publication
in the configured window. Checks happen on news cache misses (five-minute cache),
are retained in Redis for 24 hours, and remain available after a feed/model error.
An unavailable Redis cache produces unknown health rather than fabricated results.
Reachability is not fact verification. This panel covers RSS, not NewsAPI publishers.
The UI flags checks older than ten minutes and headlines older than 24 hours;
these are display policies, not trading gates.

In **Headline Validation**, label financial wording as positive/negative/neutral
or ambiguous. Open the original article, verify asset relevance and publication
information, and corroborate material claims with official issuer/exchange/regulator
sources. Mark source verified/questionable/unverified and add supporting links or
notes. Do not infer credibility automatically from a publisher's name. Predictions
are omitted from pending review responses and shown after labeling. The dashboard
and exports still show predictions: reviewers should avoid these before labeling.
The review forms are not a blinded research experiment. Reviews, notes, lists and
exports are isolated by authenticated user. Public evidence is shared; annotations
are never shared.

Metrics include only non-ambiguous labels with verified sources: per-class
precision/recall/F1/support, accuracy and a confusion matrix (human labels as rows).
Macro-F1 averages all three classes, including zero for missing classes; no eligible
labels means null accuracy/F1. Reports cover all stored reviews for that asset,
regardless of UI pagination. This is descriptive reviewer agreement, **not**
calibrated confidence, out-of-sample performance or evidence of trading profitability.

CSV and JSON exports include predictions, labels and provenance. JSON includes
metrics. CSV escapes formula-leading cells for spreadsheet opening. The export API
is paginated; the frontend collects all pages.

Authenticated routes:
- `GET /api/sentiment/health/{symbol}`
- `GET /api/sentiment/reviews/{symbol}?limit=50&offset=0`
- `PUT /api/sentiment/reviews/item/{id}` with `human_label`, `source_verdict`, `notes`
- `GET /api/sentiment/export/{symbol}?limit=1000&offset=0`

Start with 100–200 varied BTC/ETH examples. Prefer independent reviewers and retain
an untouched chronological test partition. Exact repeated headlines are suppressed,
but different headlines about one event need manual clustering to avoid leakage
and inflated sample sizes. Compare models on the same held-out examples, inspect
each class/source and assess calibration before choosing confidence cutoffs.
Automated event clustering, dual-reviewer adjudication, calibration, historical
replay and sentiment-assisted futures backtesting are future work. Trading
integration remains disabled.

## Automatic sample diagnostics

Each successful sentiment read now includes `quality`, computed on the server for
both new and cached results. It checks the selected sample's publication times,
normalized duplicate titles and URLs (ignoring UTM tracking and fragments), explicit
asset mentions, HTTPS publisher links (RSS domains must match the allowlist), valid
probabilities and consistent labels/confidence/scores, uncertainty, publisher/feed
coverage and computation age. These checks do not rewrite evidence or populate
human labels/source verdicts. No new paid services or model downloads are needed.

Policy v1 flags headlines older than 24 hours, fewer than three fresh headlines or
two publishers, sample computations older than ten minutes, top-label probability
below 60%, and top-two probability margin below 15 percentage points. These are
triage policies, not calibrated accuracy thresholds. Related events with different
titles/URLs are not automatically clustered. Fact verification, sarcasm and
asset-specific market impact are not established by these checks.

The dashboard shows **Automatic Sentiment Checks** by default. Optional labels,
accuracy metrics and exports are under **Advanced: optional accuracy review and
exports**, closed initially. Diagnostics run on sentiment load/refresh, not on a
background schedule. Source reachability remains visible even when news fails.
`checks_passed` means only the operational/sample checks passed; `model_accuracy`
remains `not_measured` and `trading_integration_enabled` remains false. Independently
labeled, held-out examples are still needed to assess model accuracy.

## RSS selection and freshness policy

Fixed feeds: `https://cointelegraph.com/rss`,
`https://www.coindesk.com/arc/outboundfeeds/rss`, `https://decrypt.co/feed`.
No keys, redirects or linked-article scraping are required. Each feed is bounded
and scanned up to 100 items. The newest 30 distinct stories are selected after
filtering and deduplication; counts therefore describe a bounded sample, not all
market news.

Deduplication canonicalizes tracking URLs and normalizes title case, punctuation,
common stop words and BTC/ETH aliases. Conservative near-title matches require
different publishers, publication times within 12 hours, at least six shared
content tokens, Jaccard similarity >= 0.8, and matching numbers/direction markers.
It is heuristic, not semantic event verification. Keep the latest representative
and show its associated publisher names; duplicate reports cannot increase its
sentiment weight. Different numbers or opposing wording are retained.

Fresh coverage needs at least three distinct fresh stories with representatives
from two publishers. An older publisher cannot satisfy fresh diversity. These
thresholds and the 12-hour half-life are transparent product policies, not
calibrated measures of predictive accuracy. Automatic diagnostics policy v2
separates intentional older context from invalid timestamps. Older-only samples
remain limited/unavailable for recent scoring. Trading integration stays disabled.

The cache key includes the new aggregation policy to invalidate old mean-based
responses. Cached RSS groups/weights and quality checks recompute against the
current time, without another model call, so headlines crossing 24 hours cannot
keep influencing a recent score. `aggregation.reference_at` is the grouping time;
`as_of` remains the original sample/inference time. Browser groups use the same
reference time. Review evidence remains immutable and scoped to each user.
