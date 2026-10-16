# CLI reference

Entry point: `nz-grocery-prices` (short alias `nzgrocery`). Python module: `python -m nzgrocery`.

| Command | Purpose |
| --- | --- |
| `stores --chain paknsave --region canterbury --json` | Offline store directory, addresses and coordinates |
| `stores --search Ilam` | Search name, suburb, city or address |
| `stores --live --chain newworld` | Use a cached live directory; download when absent/expired |
| `status --json` | List saved price snapshots and reference cache status |
| `fetch --chain newworld --store Ilam --department all` | Fetch missing daily produce/meat snapshots |
| `prices --chain newworld --store Ilam --search chicken --format json` | Read today's matching records |
| `compare --store Ilam --store Riccarton --search broccoli --department produce --json` | Lowest matching numeric price per store; check units manually |

`fetch`: `--format sqlite|csv|json|jsonl`, `--output PATH`, `--db PATH`, `--dry-run`, `--verbose`. JSON/CSV/JSONL can use `--output -`. Without a path, files go beside the cache and include chain/store/department/date. `--force` refreshes only when explicitly requested, subject to the default ten-minute interval.

`prices`: repeat `--search` for OR matching; repeat `--store` for multiple stores; `--date today|latest|YYYY-MM-DD`; `--sort price|name`; `--limit 0` for unlimited table rows; `--format table|json|csv`. `--fetch-if-missing` requires one explicit chain/store and fetches missing departments only.

Default cache: macOS `~/Library/Application Support/nz-grocery-prices/prices.sqlite`; Windows `%LOCALAPPDATA%\nz-grocery-prices\prices.sqlite`; Linux `$XDG_DATA_HOME/nz-grocery-prices/prices.sqlite` or `~/.local/share/nz-grocery-prices/prices.sqlite`. Precedence: `--db`, `NZGROCERY_DB`, `NZGROCERY_DATA`, platform default. For `fetch --format sqlite`, `--output` overrides `--db`.

The store name is resolved against the directory; its UUID goes into the API's `storeId` and store filter. Store lists and category references normally expire after seven days. `update-stores` is maintenance, not part of a normal price question.

Exit codes: 0 success (including an empty keyword result); 2 unknown/ambiguous store; 3 blocked/network/response error; 4 no usable product rows; 5 missing local snapshot. Partial results can exit 0 with missing-target warnings on stderr: report those gaps.
