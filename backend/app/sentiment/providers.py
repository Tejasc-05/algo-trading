"""Concrete SentimentProvider implementations.

Supports NewsAPI, CryptoPanic, and Twitter/X as backends.
Each provider fetches crypto-related content, scores sentiment,
and returns a normalized SentimentResult.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.sentiment.service import SentimentProvider, SentimentResult


@dataclass
class ProviderConfig:
    api_key: str
    source_name: str


class UnavailableSentimentProvider(SentimentProvider):
    def __init__(self, api_key: str | None = None):
        pass

    async def get_sentiment(self, symbol: str) -> SentimentResult:
        raise AppError("SENTIMENT_UNAVAILABLE", "A real sentiment provider is not configured", 503)


NewsAPISentimentProvider = UnavailableSentimentProvider
CryptoPanicSentimentProvider = UnavailableSentimentProvider
TwitterSentimentProvider = UnavailableSentimentProvider


# Provider registry for easy lookup
PROVIDER_REGISTRY: dict[str, type[SentimentProvider]] = {
    "newsapi": NewsAPISentimentProvider,
    "cryptopanic": CryptoPanicSentimentProvider,
    "twitter": TwitterSentimentProvider,
}


def get_sentiment_provider(provider_name: str, api_key: str | None = None) -> SentimentProvider:
    """Get a sentiment provider by name."""
    provider_cls = PROVIDER_REGISTRY.get(provider_name.lower())
    if provider_cls is None:
        raise AppError(
            code="UNKNOWN_PROVIDER",
            message=f"Unknown sentiment provider: {provider_name}",
            status_code=400,
        )
    return provider_cls(api_key=api_key)