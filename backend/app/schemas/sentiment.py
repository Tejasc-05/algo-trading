"""News evidence and headline-model probabilities; no trading signals."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Label = Literal['positive', 'negative', 'neutral']


class ArticleOut(BaseModel):
    id: str
    title: str
    summary: str
    source: str
    url: str
    published_at: datetime
    probabilities: dict[str, float] = Field(default_factory=dict)
    label: Label
    score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)


class SentimentOut(BaseModel):
    symbol: str
    score: float = Field(ge=-1, le=1)
    label: Label
    confidence: float = Field(ge=0, le=1)
    as_of: datetime
    provider: str
    model: str
    model_revision: str = 'unknown'
    articles: list[ArticleOut]
    counts: dict[str, int]
    probabilities: dict[str, float]
    quality: dict = Field(default_factory=dict)
    cached: bool = False
    window_hours: int = 24
    feed_delay_hours: int = Field(default=24, ge=0, le=168)
    inference_mode: Literal['local', 'hosted'] = 'local'
    warnings: list[str] = Field(default_factory=list)


class ReviewInput(BaseModel):
    human_label: Literal['positive', 'negative', 'neutral', 'ambiguous'] | None = None
    source_verdict: Literal['unverified', 'verified', 'questionable'] = 'unverified'
    notes: str = Field(default='', max_length=2000)
