# SQLite schema

Prefer `nz-grocery-prices prices` for normal use. Table `prices` has an integer primary key `id` plus:

`fetched_at`, `chain`, `store_id`, `store`, `department`, `category`, `name`, `price_nzd`, `unit_or_size`, `price_per`, `product_url`, `raw_price_text`, `product_id`.

A snapshot is grouped by chain, store UUID, department and `fetched_at`. Timestamps include Pacific/Auckland's offset. Historical rows remain stored. Select the latest timestamp per chain/store/department before adding filters or comparing costs. Do not sum all historical snapshots.

```sql
SELECT store, name, price_nzd, unit_or_size, price_per, fetched_at, product_url
FROM prices
WHERE chain = 'newworld' AND store LIKE '%Ilam%' AND name LIKE '%broccoli%'
ORDER BY fetched_at DESC;
```

This example returns history, not only today's records. Use CLI `prices --date today` when answering a current-price question.
