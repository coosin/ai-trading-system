# OKX Web Source Reference Map (ETH-USDT SWAP Page)

This document summarizes evidence extracted from:

- `logs/okx_eth_swap_page.html`
- key JS bundles under `logs/okx_js/`

It is intended as a practical reference for aligning our market data ingestion fields/channels.

## 1) Extracted JS Bundle Inventory

- Extracted from page HTML: `60` JS URLs (`logs/okx_js_urls.txt`)
- Successfully downloaded key trading bundles: `6`
- Core bundle family observed: `okfe/comb-trade/*`

## 2) Confirmed WebSocket Base URLs (from page HTML)

From embedded `socketBaseUrls` config in `logs/okx_eth_swap_page.html`:

- `trade`: `wss://wspri.okx.com:8443`
- `simulatedTrade`: `wss://wspripap.okx.com:8443`
- `inTrade`: `wss://wspri.okx.com:8443`
- `simulatedInTrade`: `wss://wspripap.okx.com:8443`
- `login`: `wss://wspri.okx.com:8443`
- `dex`: `wss://wsdexpri.okx.com:443`

## 3) Field/Channel Keyword Evidence (from downloaded JS)

Main findings from `logs/okx_js_analysis.txt`:

- `comb-trade__index.68b808b7.js`
  - contains: `instId`, `markPx`, `funding`, `books`, `tickers`, `trades`, `positions`, `order`, `channel`, `candle`, `kline`, `liquidation`
- `comb-trade__index.cf342a67.js`
  - contains: `instId`, `funding`, `books`, `trades`, `order`, `kline`, `algo`, `liquidation`
- `comb-trade__index.196447e5.js`
  - contains: `instId`, `trades`, `order`, `algo`
- `comb-trade__index.7b7264a6.js`
  - contains: `funding`, `books`, `trades`, `positions`, `order`, `channel`, `kline`, `liquidation`

## 4) Suggested Internal Mapping for OpenClaw

Use this as a minimum alignment target between exchange payloads and internal normalized schema:

- **Instrument identity**
  - external: `instId`
  - internal: `symbol`, `market_id`
- **Best bid/ask and last trade**
  - external: `books*`, `tickers`, `trades`
  - internal: `bid_px`, `ask_px`, `last_px`, `last_sz`, `last_ts`
- **Mark/funding**
  - external: `markPx`, `funding`
  - internal: `mark_price`, `funding_rate`, `next_funding_time`
- **OHLCV / candle**
  - external: `candle`, `kline`
  - internal: `open`, `high`, `low`, `close`, `volume`, `bar_ts`
- **Open interest / positions**
  - external: `positions` (plus related account/position stores)
  - internal: `position_size`, `entry_px`, `upl`, `upl_ratio`, `margin_mode`, `leverage`
- **Execution and order state**
  - external: `order`, `algo`
  - internal: `order_id`, `client_order_id`, `side`, `status`, `filled_sz`, `avg_fill_px`, `reduce_only`
- **Forced move monitoring**
  - external: `liquidation`
  - internal: `liq_side`, `liq_px`, `liq_sz`, `liq_ts`, `liq_intensity`

## 5) Reliability Notes

- JS files are heavily minified and code-split; some direct REST paths (for example explicit `/api/v5/...`) are not visible in fetched chunks.
- We observed intermittent CDN fetch failures (`403`/TLS EOF) when downloading bundles, so acquisition should include retry logic and stable proxy routing.
- Because page data is mostly runtime-driven, combine this source map with:
  - official API docs,
  - live WS subscription payload captures,
  - our own parser logs for final schema lock-in.

## 6) Next Action (Recommended)

Implement a lightweight "WS payload recorder" in our OKX connector:

- save first N payload samples per channel (`books`, `tickers`, `trades`, `funding-rate`, `mark-price`, `positions`)
- auto-generate a channel-field matrix
- compare matrix with this document and raise missing-field warnings

This will turn inferred mapping into evidence-based, production-safe mapping.
