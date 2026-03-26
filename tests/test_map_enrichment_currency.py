from __future__ import annotations

import asyncio

from app.map_enrichment.currency import (
    BANK_OF_TAIWAN_DAILY_RATE_URL,
    BANK_OF_TAIWAN_RATE_SOURCE,
    BankOfTaiwanTwdPriceConverter,
    parse_bank_of_taiwan_twd_rates,
)


class FakeCurrencyTextFetcher:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def fetch(self, url: str) -> str:
        self.calls.append(url)
        return self.payload


def test_parse_bank_of_taiwan_twd_rates_prefers_spot_sell_rate() -> None:
    payload = """
    幣別        匯率             現金        即期 匯率             現金        即期
    USD         本行買入     31.47500    31.80000 本行賣出     32.14500    31.95000
    JPY         本行買入      0.19080     0.19760 本行賣出      0.20360     0.20260
    PHP         本行買入      0.46350     0.00000 本行賣出      0.59550     0.00000
    """

    rates = parse_bank_of_taiwan_twd_rates(payload)

    assert rates["TWD"] == 1.0
    assert rates["USD"] == 31.95
    assert rates["JPY"] == 0.2026
    assert rates["PHP"] == 0.5955


def test_bank_of_taiwan_twd_price_converter_converts_and_caches_rates() -> None:
    payload = """
    幣別        匯率             現金        即期 匯率             現金        即期
    USD         本行買入     31.47500    31.80000 本行賣出     32.14500    32.00000
    """
    fetcher = FakeCurrencyTextFetcher(payload)
    converter = BankOfTaiwanTwdPriceConverter(fetcher=fetcher)

    first = asyncio.run(converter.convert(173, "USD"))
    second = asyncio.run(converter.convert(180, "USD"))

    assert first.source_amount == 173
    assert first.source_currency == "USD"
    assert first.display_amount == 5536
    assert first.display_currency == "TWD"
    assert first.exchange_rate == 32.0
    assert first.exchange_rate_source == BANK_OF_TAIWAN_RATE_SOURCE
    assert second.display_amount == 5760
    assert fetcher.calls == [BANK_OF_TAIWAN_DAILY_RATE_URL]
