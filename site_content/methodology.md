# Methodology

Each weekly report combines public-company market data with an independently generated strategy brief.

## Market performance

Prices and market capitalizations come from Massive. Returns are calculated over 3-, 12-, and 24-month horizons against the S&P 500 (`SPY`). Companies are ranked across the full watchlist and within each category. The comparison baseline is the latest earlier final report at least five days old. Rank changes use the stored published ranks, so adding or removing a ticker cannot silently rewrite last week's order.

The watchlist is the YAML front matter in `inputs/companies.md`. Tickers are U.S. listings or ADRs. Categories follow the corn-to-ethanol value chain: crop inputs, grain origination, ethanol production, wet milling and co-products, blending and retail, advanced biofuels, international ethanol, and logistics.

## Earnings

Upcoming and recently reported earnings dates are collected from public Google Finance pages, with Yahoo Finance as the date fallback. Tentative dates are labeled when a source has not confirmed the next event.

## Strategy narrative

The strategy brief is produced with the OpenAI Responses API, high reasoning, and built-in web search. The version-controlled master prompt is `inputs/ethanol-strategy-prompt.md`. Each request includes the report date, the prior seven-day window, up to four earlier ethanol briefs as untrusted reference material, and a nearby-futures tape.

Nearby corn, CBOT ethanol, RBOB, and Henry Hub settlements are retrieved from Yahoo Finance delayed futures and shown on the report. Nearby corn is treated as the market's current perception of yield and demand risk and is passed into the briefing prompt so the lead assessment has to be consistent with the tape. Other commodity prices, RINs, crush margins, EIA, and USDA figures in the narrative still come from the model's web search of public sources. If a reliable public value is not available, the brief is instructed to say so rather than invent one. The prompt ranks USDA balance-sheet evidence above noisy weekly prints, but still quotes concrete levels when they are available.

If the API call fails, the last successful narrative is reused and the report is marked degraded. A failed call never overwrites the latest good strategy archive.

## Farmer Corn Brief

The same Thursday run also generates a narrative-only Farmer Corn Brief from `inputs/farmer-strategy-prompt.md`. It uses the same model, tape, and reporting window, but a different audience: a Nebraska producer who is long corn. History is isolated to prior farmer briefs so ethanol plant-margin language cannot leak into the prompt. The published page is the brief itself—no company tables, earnings, or charts. It is stored under `reports/final/farmer/`, shown on the homepage, and listed as its own group on Past reports. If the farmer call fails, the ethanol intel report still publishes; that week is simply omitted from the farmer archive.

## Publication

Reports are stored by date under `reports/final/`. Farmer briefs live under `reports/final/farmer/`. The public site is generated into `docs/` and published with GitHub Pages. PDF and self-contained HTML downloads are created from the same dated report. The News & Earnings index covers the ethanol intel report only and assigns headlines to topics with deterministic keyword rules, not a separate classifier.
