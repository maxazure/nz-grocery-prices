# Release validation — 0.1.0

Checked on 2026-10-17 (Pacific/Auckland), macOS arm64, Python 3.13.

- 76 offline tests passed: parsing, store resolution, daily cache, exports, partial-data reporting, request timeout, selected store ID on every page, HTTP errors without automatic retries or credential output, and incomplete-page rejection.
- Skill frontmatter validation passed; all three discovery copies match the canonical skill.
- Wheel and source archive build and `twine check` passed. Skill ZIP has `SKILL.md` at its root.
- Live direct HTTP requests used guest credentials obtained through the website endpoint. No browser, personal account or manually supplied token was used.
- New World Ilam: 167 produce rows and 89 meat/seafood rows after category filtering.
- PAK’nSAVE Riccarton: 222 produce rows and 290 meat/seafood rows after category filtering.
- Repeating Riccarton `fetch --department all` returned `cached: true` for both departments.
- Each catalogue search supplied the selected store UUID as both `storeId` and a store filter. These tests verify the returned API observations; they do not independently audit shelf or checkout prices.
- The API's existing `category0NI` / `NI_POPULARITY_ASC` fields returned data for these South Island stores. Those upstream field names are preserved.

Price snapshots and guest credentials are not included in this repository or release artifacts.

Not yet verified: every store, every network, WorkBuddy end-to-end skill installation, and ChatGPT Work end-to-end execution. macOS/Windows/Linux CI checks cover offline behavior; consult the repository Actions tab for their current results. No claim is made that all cloud execution environments permit these endpoints.
