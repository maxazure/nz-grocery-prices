# Troubleshooting

- **Command not found:** install the release in the current execution environment, or invoke the full virtualenv executable path. A skill ZIP contains instructions; it does not install Python or the CLI.
- **No terminal or package installation:** use local WorkBuddy/Codex or a host that exposes command execution. A web-search tool alone cannot execute this CLI. For ChatGPT, read the repository's compatibility notes; do not promise all Work environments support installation.
- **HTTP 401/403/429, challenge or timeout:** report the status and stop. No automatic retries, browser fallback or account login. Do not print or persist guest credentials. A network may work locally but be rejected from a cloud environment.
- **Python TLS/certificate error:** use a correctly configured Python installation and CA trust; never disable certificate verification.
- **Exit 2:** inspect `stores` and use a precise name or UUID.
- **Exit 4:** no usable rows were returned. Do not infer zero price or no stock.
- **Exit 5 / partial-data note:** fetch only the missing store/department once. `--date latest` reads old data and must be labelled with its actual date.
- **Unexpected total:** inspect pack sizes, units, quantities and membership/multibuy conditions. `compare` does not normalise units; unpriced ingredients must remain outside the subtotal.
- **Windows time zone error:** install the package dependencies, including `tzdata`, in the same Python environment.
