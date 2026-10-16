# nz-grocery-prices

查附近的 **PAK’nSAVE 和 New World** 蔬果、鲜肉与海鲜网上价格，让 AI 根据你的口味、预算和饮食偏好整理采购清单。

这是一个 **AI Skill + Python 命令行工具**。Skill 告诉 AI 如何安装工具、选择门店和使用真实价格；命令行工具直接查询超市网站使用的访客 API，并把结果保存在你自己的电脑上。无需浏览器、超市账号或个人 API key。

[下载 Skill ZIP](https://github.com/maxazure/nz-grocery-prices/releases/latest/download/nz-grocery-prices-skill.zip) · [查看发布版本](https://github.com/maxazure/nz-grocery-prices/releases) · [English](#english)

## 直接把这段话发给 AI

适用于能运行本地命令、安装 Python 工具并联网的 WorkBuddy 或 Codex。安装时可能需要确认权限；执行时间取决于环境与门店商品数量。

```text
请阅读 https://github.com/maxazure/nz-grocery-prices 的 README，
安装仓库 skills/nz-grocery-prices 中的 skill，并按说明安装命令行工具。
先检查当前环境是否能运行 Python 和访问超市 API；缺少条件请明确告诉我。

我住在新西兰 Christchurch 的 Avonhead。
请找附近的 New World 和 PAK’nSAVE，各选一家合适的门店，说明名称和地址。
查询今天的蔬菜和肉类网上价格。

我最近在锻炼，希望少吃添加糖、每餐有蛋白质，喜欢川菜。
请按一人份安排三天晚餐，列出食材、购买数量、价格和预计总花费。
标明门店、商品规格、查询日期和来源链接。
区分每公斤价、每件价和整包价格；注明会员优惠的适用条件。
调料、米饭等查不到价格的食材单独列出，不要猜价格或把它们算作免费。
如果今天的数据无法取得，明确说明，不要用旧价格冒充今天的价格。
```

把地区、人数、天数和口味换成自己的需求即可。菜单由你使用的 AI 整理；本工具提供门店和商品价格，不提供营养检测或精确的个人营养方案。

## 安装 Skill

### WorkBuddy

1. 从 [WorkBuddy 官网](https://www.workbuddy.cn/)下载并打开软件。
2. 将上面的提示词交给有本地文件及终端权限的会话，使用仓库内 `skills/nz-grocery-prices` 目录。
3. 如果当前版本提供上传 Skill 的入口，可以上传本仓库 Release 的 `nz-grocery-prices-skill.zip`，然后要求 AI 按技能说明安装命令行工具。
4. 检查 AI 是否实际运行了工具并返回门店、时间和商品链接。首次运行需要完成 Python 环境安装；只上传 ZIP 不会自动安装命令行工具。

克隆整个仓库作为工作目录时，仓库内 `.workbuddy/skills/nz-grocery-prices` 已附带相同技能。不同版本的识别和启用方式可能不同。

### Codex

可直接要求 Codex 从上述 GitHub URL 安装 `skills/nz-grocery-prices`。也可克隆仓库并在其中启动 Codex，使用 `.agents/skills/nz-grocery-prices`，或把技能目录复制到 `~/.agents/skills/nz-grocery-prices`。如技能列表未更新，重新开始会话。随后让 Codex 按技能说明安装命令行工具。

### ChatGPT Work 能直接使用吗？

**需要确认所用 ChatGPT 界面支持技能安装，并且当前执行环境能运行 Python 和访问外部 API。** 把提示词粘贴进普通聊天，不代表技能已安装，也不代表已经执行查价。

- OpenAI 文档将独立 skill 的使用入口列在 ChatGPT 桌面应用、Codex CLI 和 IDE 扩展；通过插件分发的 skills 可用于网页、桌面和移动端的 Chat / Work。以你的账号和工作区实际可用入口为准。
- 本项目目前分发 GitHub 源码和独立 Skill ZIP，**尚未上架 ChatGPT 插件目录**。不要把 ZIP 上传为聊天附件后就当作已启用的插件。
- 查价需要 Python 3.10+、安装包的能力、可写本地目录，以及对 GitHub 和四个超市域名的 HTTPS 访问。企业工作区可能限制安装或网络访问；只具备网页搜索能力的会话不能运行此 CLI。
- 此版本直接使用 HTTP API，**不需要 Chromium 或 Playwright**。云端网络仍可能被超市拒绝；本机成功不保证每个云端环境成功。
- 如果当前环境不满足条件，可在本地 WorkBuddy / Codex 运行，导出 CSV 或 JSON，再交给 ChatGPT 分析。上传文件时请保留门店与查询时间。

依据：[OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills)、[Plugins](https://learn.chatgpt.com/docs/plugins)。本项目没有完成所有 ChatGPT 账号、版本和云端环境的端到端验证。

## 安装命令行工具

Python **3.10+**。当前发布渠道是 GitHub；不要假定已有同名 PyPI 包。

使用已有的 [uv](https://docs.astral.sh/uv/) 安装固定版本：

```sh
uv tool install "git+https://github.com/maxazure/nz-grocery-prices.git@v0.1.1"
nz-grocery-prices --version
nz-grocery-prices stores --region canterbury --search Ilam
```

也可用 `pipx install "git+https://github.com/maxazure/nz-grocery-prices.git@v0.1.1"`。上述 Git URL 安装方式需要 Git。没有 Git 时可下载 Release 的 wheel，使用 `pipx install /path/to/nz_grocery_prices-0.1.1-py3-none-any.whl`。

只有 Python 时，在下载的源码目录建立虚拟环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/nz-grocery-prices --help
```

Windows PowerShell 对应：

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\nz-grocery-prices.exe --help
```

macOS/Linux 的网络请求使用 Python 标准库；Windows 额外安装 `tzdata`，用于新西兰时区。若提示找不到命令，使用安装环境中的完整路径。不要把包装到另一个无法访问的云端或 Python 环境后，误认为当前 AI 已经能运行它。

## 使用示例

### 1. 选门店

```sh
nz-grocery-prices stores --region canterbury --chain newworld
nz-grocery-prices stores --region canterbury --chain paknsave
nz-grocery-prices stores --search Riccarton --json
```

随包附带 207 家门店记录（PAK’nSAVE 58 家、New World 149 家，源数据日期 2026-10-12），含地址和网站提供的经纬度。查询门店默认离线完成。门店表用于选店，不保证每家都能成功返回商品。

Avonhead 示例可考虑 New World Ilam / Fendalton、PAK’nSAVE Riccarton / Hornby。只提供 suburb 时无法确定离你家最近的一家；请按实际出发点选择。本工具没有地图路线或驾车距离功能。

`--store` 接受完整 UUID 或门店名片段。同名结果会要求进一步指定，避免默默选错店。门店缺失时才使用 `stores --live --chain newworld`。

### 2. 查询今天的价格

```sh
nz-grocery-prices status --json
nz-grocery-prices fetch --chain newworld --store Ilam --department all
nz-grocery-prices fetch --chain paknsave --store Riccarton --department all
```

`produce` 查询蔬果，`meat` 查询鲜肉、禽肉和海鲜，`all` 查询两类。暂不覆盖全店杂货、鸡蛋、牛奶、米面、调料或所有冷冻食品。商品分类以超市返回的数据为准，部分熟食、肉类替代品等被排除。

每个门店、品类按 **Pacific/Auckland 当天日期**保存快照。同一天重复查询复用缓存；当天缺失才联网，每次请求间隔 2–4 秒。不会为每个问题重复联网。

### 3. 按食材查价或比较

```sh
nz-grocery-prices prices --chain newworld --store Ilam --search broccoli --format json
nz-grocery-prices prices --chain paknsave --store Riccarton --search chicken --department meat
nz-grocery-prices compare --store Ilam --store Riccarton --search broccoli --department produce --json
```

商品名通常是英文；AI 应把食材名称转换成相应查询词。`prices` 和 `compare` 默认只读本地数据。缺少当天快照时按提示运行 `fetch`，或对明确的一家店使用 `prices --chain ... --store ... --fetch-if-missing`。

`compare` 返回每个门店中关键词匹配的最低标价，**不会自动把整包价和公斤价换算成同一规格**。采购建议仍需核对 `unit_or_size`、`price_per` 和促销条件，不能仅凭最低数字就说哪家更便宜。

### 4. 导出给 ChatGPT 或表格软件

```sh
nz-grocery-prices prices --chain newworld --store Ilam --format csv > ilam-prices.csv
nz-grocery-prices prices --chain paknsave --store Riccarton --format json > riccarton-prices.json
```

结果包含 `fetched_at`、`chain`、`store_id`、`store`、`department`、`category`、`name`、`price_nzd`、`unit_or_size`、`price_per`、`product_url`、`raw_price_text`、`product_id`。金额单位为 NZD。`raw_price_text` 保留促销、多买优惠和会员条件。

## 缓存与常见问题

默认数据库是 `prices.sqlite`：

| 系统 | 目录 |
| --- | --- |
| macOS | `~/Library/Application Support/nz-grocery-prices/` |
| Windows | `%LOCALAPPDATA%\nz-grocery-prices\` |
| Linux | `$XDG_DATA_HOME/nz-grocery-prices/`，未设置时为 `~/.local/share/nz-grocery-prices/` |

`NZGROCERY_DATA` 可指定数据目录；`NZGROCERY_DB` 可指定数据库完整路径；单次 `--db` 优先。门店表与分类参考缓存通常保留 7 天。

| 现象 / 退出码 | 处理 |
| --- | --- |
| `0` | 查询成功，或已复用缓存；没有匹配商品时也可能为 0，需读提示 |
| `2`：门店不存在或不明确 | 用 `stores` 查看候选并指定 UUID |
| `3`：HTTP 401/403/429、超时或响应异常 | 停止请求，检查网络或稍后再试；不要绕过验证或连续重试 |
| `4`：没有可用商品 | 明确告知没有取得该品类价格，不据此推断门店没有库存 |
| `5`：当天快照缺失 | 按命令提示为该门店、品类运行一次 `fetch` |

部分门店或品类缺失时，读命令可能返回已有行并向 stderr 提示缺失项。AI 必须披露缺失项。`--date latest` 可读取旧数据，输出中必须保留实际日期。明确需要当天重新取价时才使用 `fetch --force`；默认十分钟内不重复刷新。

价格是所选门店在查询时返回的网上标价，可能与现场、会员价及实际结算不同；查询不代表库存保证。工具不会登录、下单或加入购物车。遇到访问限制时停止，不处理验证码。

## 开发与验证

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python scripts/sync_skills.py --zip
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*.whl dist/*.tar.gz
```

技能的唯一编辑入口是 `skills/nz-grocery-prices/`；`scripts/sync_skills.py` 同步到 `.agents/skills/`、`.claude/skills/`、`.workbuddy/skills/`，并可构建上传 ZIP。测试使用离线样本。发布验证记录见 [VALIDATION.md](VALIDATION.md)。

实现直接调用网站的访客入口 `/api/user/get-current-user`，仅在内存中使用访客凭据，再访问 `api-prod.paknsave.co.nz/v1/edge` 或 `api-prod.newworld.co.nz/v1/edge`。不保存 token、Cookie 或用户账号。底层接口可能变化，出现错误请附上脱敏后的命令、门店和错误码提交 issue。

## English

**Store-specific NZ grocery prices for PAK’nSAVE and New World**, packaged as an agent skill and a Python CLI. Find a store, fetch fresh produce and meat/seafood prices, and let your AI prepare a shopping list using real product sizes, dates and links.

- Python 3.10+; direct HTTP guest API access. No browser, supermarket login or personal API key required.
- Install from the GitHub release/tag above; this project does not currently promise a PyPI installation route.
- Import the release Skill ZIP into a compatible host, or install `skills/nz-grocery-prices`. The skill and CLI must both be available in the host's execution environment.
- WorkBuddy and local Codex need terminal, filesystem and HTTPS access. ChatGPT Work availability depends on skill/plugin installation support and its actual execution environment; this repository is not listed in the ChatGPT plugin directory. A chat attachment alone is not an installed skill. Export CSV/JSON locally if your chat cannot execute Python or reach the APIs.
- Use `stores`, then `fetch --chain newworld --store Ilam --department all`. Query saved data with `prices`; use `compare` only after checking unit and pack-size differences.
- Today's Pacific/Auckland snapshots are reused. Requests are sequential and spaced 2–4 seconds apart. Missing or blocked data must be reported rather than invented.
- Prices are online observations, not stock guarantees or checkout quotes. Membership and multibuy conditions remain in `raw_price_text`. Pantry items and nutrition data are outside the current catalogue scope.

MIT license. Independent community project, not affiliated with Foodstuffs, PAK’nSAVE or New World. Follow the source sites' applicable terms. The software license covers this code, not rights to redistribute supermarket data. No bulk price dataset is distributed in releases.
