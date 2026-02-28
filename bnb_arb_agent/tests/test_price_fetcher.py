"""Unit tests for DEXPriceFetcher fallback chain."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from tools.price_fetcher import DEXPriceFetcher


class TestDEXPriceFetcherSubgraph:
    @patch("tools.price_fetcher.requests.post")
    def test_returns_derived_usd_from_subgraph(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"token": {"derivedUSD": "614.25", "tokenDayData": []}}},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        fetcher = DEXPriceFetcher(use_testnet=False)
        with patch.object(fetcher._router.functions, "getAmountsOut", side_effect=Exception("unused")):
            price = fetcher._price_from_subgraph("BNB")

        assert price == pytest.approx(614.25)

    @patch("tools.price_fetcher.requests.post", side_effect=requests.ConnectionError("timeout"))
    def test_returns_zero_on_all_subgraph_failures(self, _mock_post):
        fetcher = DEXPriceFetcher(use_testnet=False)
        assert fetcher._price_from_subgraph("BNB") == 0.0


class TestDEXPriceFetcherRouter:
    def test_returns_zero_for_unknown_symbol(self):
        fetcher = DEXPriceFetcher(use_testnet=False)
        assert fetcher._price_from_router("UNKNOWN_TOKEN") == 0.0


class TestGetDEXPriceFallbackOrder:
    @patch.object(DEXPriceFetcher, "_price_from_subgraph", return_value=0.0)
    @patch.object(DEXPriceFetcher, "_price_from_router",   return_value=612.5)
    def test_falls_back_to_router_when_subgraph_fails(self, _mock_router, _mock_subgraph):
        fetcher = DEXPriceFetcher(use_testnet=False)
        assert fetcher.get_dex_price("BNB") == pytest.approx(612.5)

    @patch.object(DEXPriceFetcher, "_price_from_subgraph", return_value=0.0)
    @patch.object(DEXPriceFetcher, "_price_from_router",   return_value=0.0)
    def test_returns_zero_when_all_sources_fail(self, _mock_router, _mock_subgraph):
        fetcher = DEXPriceFetcher(use_testnet=False)
        assert fetcher.get_dex_price("BNB") == 0.0
