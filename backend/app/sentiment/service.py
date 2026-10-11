"""Stable provider facade for news sentiment; never executes trading orders."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class SentimentResult:
    symbol: str
    score: float  # -1 (very negative) .. 1 (very positive)
    label: Literal["positive", "negative", "neutral"]
    confidence: float  # 0..1
    as_of: datetime
    model_revision: str = 'unknown'
    provider: str = 'newsapi'
    model: str = 'ProsusAI/finbert'
    articles: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    probabilities: dict = field(default_factory=dict)
    feed_delay_hours: int = 24
    inference_mode: str = 'local'
    warnings: list[str] = field(default_factory=list)
    window_hours: int = 24


class SentimentProvider(ABC):
    @abstractmethod
    async def get_sentiment(self, symbol: str) -> SentimentResult: ...


class SentimentService:
    """Thin facade the rest of the app depends on instead of a concrete
    provider — swap `provider` to change the sentiment source without
    touching any caller."""

    def __init__(self, provider: SentimentProvider):
        self._provider = provider

    async def get_sentiment(self, symbol: str) -> SentimentResult:
        return await self._provider.get_sentiment(symbol)
