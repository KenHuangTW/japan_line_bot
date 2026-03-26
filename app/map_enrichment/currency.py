from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

import httpx

from app.lodging_links.resolver import DEFAULT_BROWSER_HEADERS

BANK_OF_TAIWAN_DAILY_RATE_URL = "https://rate.bot.com.tw/xrt/fltxt/0/day"
BANK_OF_TAIWAN_RATE_SOURCE = "bank_of_taiwan_spot_sell"
ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "TWD", "VND", "IDR"}


@dataclass(frozen=True)
class ConvertedPrice:
    source_amount: float
    source_currency: str | None
    display_amount: float
    display_currency: str | None
    exchange_rate: float | None = None
    exchange_rate_source: str | None = None


class CurrencyTextFetcher(Protocol):
    async def fetch(self, url: str) -> str: ...


class HttpCurrencyTextFetcher:
    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    async def fetch(self, url: str) -> str:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=DEFAULT_BROWSER_HEADERS,
            timeout=self.timeout,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text


class PriceConverter(Protocol):
    async def convert(self, amount: float, currency: str | None) -> ConvertedPrice: ...


class BankOfTaiwanTwdPriceConverter:
    def __init__(
        self,
        fetcher: CurrencyTextFetcher | None = None,
        *,
        timeout: float = 5.0,
        cache_ttl: timedelta = timedelta(hours=6),
    ) -> None:
        self.fetcher = fetcher or HttpCurrencyTextFetcher(timeout=timeout)
        self.cache_ttl = cache_ttl
        self._cache: tuple[datetime, dict[str, float]] | None = None
        self._lock = asyncio.Lock()

    async def convert(self, amount: float, currency: str | None) -> ConvertedPrice:
        normalized_currency = _normalize_currency_code(currency)
        source_amount = float(amount)
        if normalized_currency is None:
            return ConvertedPrice(
                source_amount=source_amount,
                source_currency=None,
                display_amount=source_amount,
                display_currency=None,
            )

        if normalized_currency == "TWD":
            return ConvertedPrice(
                source_amount=source_amount,
                source_currency="TWD",
                display_amount=_round_amount(source_amount, "TWD"),
                display_currency="TWD",
            )

        rates = await self._get_cached_rates()
        rate = rates.get(normalized_currency)
        if rate is None:
            return ConvertedPrice(
                source_amount=source_amount,
                source_currency=normalized_currency,
                display_amount=source_amount,
                display_currency=normalized_currency,
            )

        converted_amount = _round_amount(source_amount * rate, "TWD")
        return ConvertedPrice(
            source_amount=source_amount,
            source_currency=normalized_currency,
            display_amount=converted_amount,
            display_currency="TWD",
            exchange_rate=rate,
            exchange_rate_source=BANK_OF_TAIWAN_RATE_SOURCE,
        )

    async def _get_cached_rates(self) -> dict[str, float]:
        cached = self._cache
        now = datetime.now(timezone.utc)
        if cached is not None and now - cached[0] < self.cache_ttl:
            return cached[1]

        async with self._lock:
            cached = self._cache
            now = datetime.now(timezone.utc)
            if cached is not None and now - cached[0] < self.cache_ttl:
                return cached[1]

            payload = await self.fetcher.fetch(BANK_OF_TAIWAN_DAILY_RATE_URL)
            rates = parse_bank_of_taiwan_twd_rates(payload)
            self._cache = (now, rates)
            return rates


def parse_bank_of_taiwan_twd_rates(payload: str) -> dict[str, float]:
    rates: dict[str, float] = {"TWD": 1.0}
    for raw_line in payload.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("幣別"):
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        currency = _normalize_currency_code(parts[0])
        if currency is None:
            continue

        try:
            sell_index = parts.index("本行賣出")
        except ValueError:
            continue

        cash_sell = _parse_positive_float(parts[sell_index + 1]) if len(parts) > sell_index + 1 else None
        spot_sell = _parse_positive_float(parts[sell_index + 2]) if len(parts) > sell_index + 2 else None
        rate = spot_sell or cash_sell
        if rate is not None:
            rates[currency] = rate

    return rates


def _normalize_currency_code(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().upper()
    if normalized in {"NT$", "NTD"}:
        return "TWD"
    if len(normalized) == 3 and normalized.isalpha():
        return normalized
    return None


def _parse_positive_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _round_amount(amount: float, currency: str | None) -> float:
    normalized_currency = _normalize_currency_code(currency)
    if normalized_currency in ZERO_DECIMAL_CURRENCIES:
        quantum = Decimal("1")
    else:
        quantum = Decimal("0.01")
    return float(Decimal(str(amount)).quantize(quantum, rounding=ROUND_HALF_UP))
