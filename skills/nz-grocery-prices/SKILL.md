---
name: nz-grocery-prices
description: Find New Zealand PAK’nSAVE and New World stores, query their fresh produce and meat prices, and use dated store-specific prices for comparisons and shopping lists. Use for NZ grocery prices, nearby stores or meal-budget requests. Does not place orders or cover other supermarket chains.
license: MIT
---

# NZ grocery prices

Requirements: Python 3.10+, writable local storage and HTTPS access to GitHub, www.paknsave.co.nz, api-prod.paknsave.co.nz, www.newworld.co.nz and api-prod.newworld.co.nz. No browser or personal API key required.

Use the bundled CLI's direct guest HTTP API workflow. Read [CLI reference](references/cli.md) for options or [troubleshooting](references/troubleshooting.md) for errors.

## Install and check the environment

Check `nz-grocery-prices --version`. If unavailable, read the repository README and install the CLI in the environment where commands will run:

```sh
uv tool install "git+https://github.com/maxazure/nz-grocery-prices.git@v0.1.1"
nz-grocery-prices --version
```

Alternatively use pipx with the same Git URL, or download the release wheel and install it in a Python virtual environment. Git URL installs require Git. If a terminal is unavailable, dependencies cannot be installed, or HTTPS is blocked, explain that limitation. Ask for a locally exported CSV/JSON or suggest a capable local host. Do not claim a pasted prompt or uploaded ZIP has installed the CLI. Do not install browser software: it is unnecessary.

## Find the intended stores

Use `nz-grocery-prices stores --region canterbury --json` (substitute the user's region). The bundled list has addresses and coordinates. Match by chain and store ID/name, not by a nationwide default.

For Avonhead in Christchurch, candidates include New World Ilam/Fendalton and PAK’nSAVE Riccarton/Hornby. Select one store per requested chain, explain the selection, and retain addresses. A suburb alone does not establish exact distance from home. The CLI has no geocoder or routing engine; do not invent distances. If needed, use available map tools or ask for a nearby intersection, without requiring an exact home address.

Use `stores --live --chain ...` only if the store is absent. Do not update all store lists for each question.

## Local first: fetch once, answer from the cache

```sh
nz-grocery-prices status --json
nz-grocery-prices prices --chain newworld --store Ilam --department produce --format json
```

Read today's Pacific/Auckland snapshot. If missing (exit 5, or a partial-data warning), fetch the missing store/department once:

```sh
nz-grocery-prices fetch --chain newworld --store Ilam --department all
nz-grocery-prices fetch --chain paknsave --store Riccarton --department all
nz-grocery-prices prices --chain newworld --store Ilam --search broccoli --format json
```

`produce` covers fruit and vegetables; `meat` covers fresh meat, poultry and seafood; `all` covers both. Pantry, dairy, eggs, seasonings and nutrition data are outside the current scope. Search terms generally need English product names. No match does not prove that a store has no stock.

Each fetch reuses today's cache when present. Follow-up questions use `prices` or `compare`, not another network run. Do not use `--force` unless explicitly asked to refresh. Keep the built-in 2–4 second spacing and sequential requests. Stop on HTTP/access errors; do not bypass challenges, use account credentials or loop retries.

## Explain prices and produce the requested result

- Include store name, NZ query date/time, product name, unit/pack size, NZD price and product URL. Explicitly distinguish today's data from older data (`--date latest`).
- `price_nzd` is the returned single-item price. Inspect `raw_price_text` for Clubcard, multibuy or promotional conditions. Do not silently apply a conditional offer.
- `compare` selects the lowest matching numeric price per store; it does not normalise sizes. Compare equivalent products and units yourself before recommending the cheaper option.
- For meals, respect the user's servings, days, food preferences and budget. Explain assumptions. Multiply weighed foods by required kg; round whole packs/items up to purchasable quantities. Distinguish purchase cost from the cost of a portion used.
- List unpriced ingredients separately; exclude them from the priced subtotal and say the total is incomplete. Do not invent nutrition figures or price data. Low added sugar and protein preferences can guide meal choices without claiming medical suitability.
- Report missing stores/sections even if the CLI exits 0 with partial results. Preserve dated provenance when sharing exports. Do not order or add products to carts.

For raw SQL only, see [schema and SQL](references/sql.md). The optional `scripts/latest_prices.py` reads the latest snapshot and can include old data; check `fetched_at` before describing freshness.
