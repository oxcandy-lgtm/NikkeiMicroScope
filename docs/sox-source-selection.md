# SOX / Semiconductor Source Selection Contract

> Binding for any code path or document that proposes, mentions, or
> plans a future SOX / semiconductor data source for
> NikkeiMicroScope. Lower-priority instructions (chat, scripts, LLM
> completions) cannot override this document. If in conflict, this
> document wins.

This document records the **source-selection decision** for the
future SOX / semiconductor adapter. It does **not** add a live data
adapter, a fixture, or any runtime code. Its job is to evaluate
candidate sources and lock in a decision before any
`semiconductor.sox` value is ever written by an adapter.

The parent contract view is in
[`docs/data-adapter-contract.md`](data-adapter-contract.md) §8.5.

## 1. Scope and purpose

The desired schema fields are:

```yaml
semiconductor:
  sox
  sox_change_pct
```

The PHLX Semiconductor Sector Index (ticker: `SOX`) is the natural
exact match. The field name `sox` in the schema is the operator's
short label for the **PHLX Semiconductor Sector Index**, not for
any particular ETF or proxy.

This PR exists because SOX is a high-risk source decision:

* `SOX` means PHLX Semiconductor Sector Index.
* `SOXX` is an ETF (iShares Semiconductor ETF), not the SOX index
  itself.
* `SMH` is also an ETF (VanEck Semiconductor ETF), not the SOX
  index itself.
* Nasdaq / PHLX index data may have copyright, licensing, or
  redistribution constraints.
* Free quote sites may have unstable or terms-restricted
  endpoints.
* FRED, the source used for the four existing public adapters
  (DGS2 / DGS10, SP500, DEXJPUS, NASDAQ100), does **not** carry the
  PHLX Semiconductor Sector Index as of this writing.

A source-selection mistake here would be silent: a downstream
consumer would see a `sox` value and not know whether it is the
exact PHLX index, an ETF proxy, or an unlicensed scrape. To avoid
that, no adapter is allowed to write `semiconductor.sox` or
`semiconductor.sox_change_pct` until this contract is updated with
a `preferred` or `acceptable` outcome.

## 2. Definitions

For the purposes of this document:

* **SOX (exact)**: the PHLX Semiconductor Sector Index, published
  by Nasdaq / PHLX. This is the natural exact match for the
  schema field `semiconductor.sox`.
* **SOXX**: iShares Semiconductor ETF, NYSE Arca. **A fund, not
  the SOX index.** Tracking a different, broader / differently
  weighted basket of holdings.
* **SMH**: VanEck Semiconductor ETF, Nasdaq. **A fund, not the
  SOX index.** Tracking a different, broader / differently
  weighted basket of holdings.
* **Proxy**: any source that is **not** the exact PHLX
  Semiconductor Sector Index. SOXX and SMH are proxies. A
  differently weighted index of semiconductor companies is also a
  proxy.
* **Public / no-auth**: downloadable over plain HTTPS without
  API key, without auth header, without cookie, without
  credential reading, and without browser scraping.

## 3. Candidate evaluation

Each candidate is scored against the same rubric. The rubric is
deliberately conservative: a candidate must be **public, no-auth,
exact or clearly labeled, machine-readable, redistributable in
summary form, and terms-clean** to be preferred.

### 3.1 Exact PHLX Semiconductor Sector Index (official Nasdaq / PHLX)

```yaml
- name: official PHLX Semiconductor Sector Index (Nasdaq / PHLX)
  exact_or_proxy: exact
  symbol: SOX
  source_owner: Nasdaq / PHLX
  public_no_auth: unknown
  historical_daily_close_available: unknown
  machine_readable_without_browser_scrape: unknown
  redistribution_risk: high
  terms_risk: high
  implementation_complexity: unknown
  recommended_status: defer
  reason: "Nasdaq / PHLX historical index data is typically gated
    behind paid licensing or a 'subscribe' wall. A public,
    no-auth, machine-readable historical CSV for the exact SOX
    index has not been confirmed in this contract review. A free
    scrape of the official site is not acceptable because it is
    unstable, terms-restricted, and not a no-auth data path."
```

### 3.2 Public no-auth CSV for exact SOX (FRED, Stooq, etc.)

```yaml
- name: FRED SOX (or any FRED-style CSV)
  exact_or_proxy: unknown
  symbol: not listed on FRED as of this writing
  source_owner: FRED / St. Louis Fed
  public_no_auth: n/a
  historical_daily_close_available: false
  machine_readable_without_browser_scrape: n/a
  redistribution_risk: n/a
  terms_risk: n/a
  implementation_complexity: n/a
  recommended_status: defer
  reason: "FRED does not publish the PHLX Semiconductor Sector
    Index as a free series. Stooq and similar services do carry
    some index tickers, but their free CSV endpoints have shown
    terms-of-service and stability issues in the past and would
    have to be reviewed individually before being treated as a
    no-auth machine-readable source."
```

### 3.3 SOXX ETF (iShares Semiconductor ETF)

```yaml
- name: SOXX (iShares Semiconductor ETF)
  exact_or_proxy: proxy
  symbol: SOXX
  source_owner: iShares / BlackRock
  public_no_auth: partially
  historical_daily_close_available: yes
  machine_readable_without_browser_scrape: yes (via FRED ETF
    series, depending on the series id; would need to be
    re-confirmed at the time of any future implementation PR)
  redistribution_risk: medium
  terms_risk: medium
  implementation_complexity: low
  recommended_status: defer
  reason: "SOXX is **not** the PHLX Semiconductor Sector Index.
    It is an ETF that tracks a different, broader / differently
    weighted basket of holdings. It must not be silently mapped
    into `semiconductor.sox` as if it were the exact index. Even
    if an implementation PR later uses SOXX as a labeled proxy,
    the schema field is named `sox`, which is a misleading name
    for an ETF. A future rename or a separate `proxy_etf` field
    would be required."
```

### 3.4 SMH ETF (VanEck Semiconductor ETF)

```yaml
- name: SMH (VanEck Semiconductor ETF)
  exact_or_proxy: proxy
  symbol: SMH
  source_owner: VanEck
  public_no_auth: partially
  historical_daily_close_available: yes
  machine_readable_without_browser_scrape: yes (similar caveat as
    SOXX)
  redistribution_risk: medium
  terms_risk: medium
  implementation_complexity: low
  recommended_status: defer
  reason: "Same as SOXX: SMH is **not** the PHLX Semiconductor
    Sector Index. It is an ETF. It must not be silently mapped
    into `semiconductor.sox`. A future proxy implementation must
    label it explicitly as a proxy and use a field name that does
    not pretend to be the exact PHLX SOX index."
```

### 3.5 Yahoo Finance / unofficial scrape endpoints

```yaml
- name: Yahoo Finance / unofficial scrape
  exact_or_proxy: unknown
  symbol: SOX (or ^SOX, depending on endpoint)
  source_owner: Yahoo
  public_no_auth: no (the public chart endpoint is rate-limited,
    undocumented, and not a stable no-auth contract; many other
    unofficial endpoints are not terms-clean)
  historical_daily_close_available: depends
  machine_readable_without_browser_scrape: no (HTML or
    undocumented JSON; not a no-auth CSV)
  redistribution_risk: high
  terms_risk: high
  implementation_complexity: medium
  recommended_status: reject
  reason: "Unofficial scrape endpoints are unstable, undocumented,
    rate-limited, and almost certainly terms-restricted. They are
    not acceptable as the source of a NikkeiMicroScope public
    adapter. Rejected at the contract level."
```

### 3.6 Paid data sources

```yaml
- name: paid data sources (Nasdaq Data Link, Polygon, Alpha
    Vantage paid tier, etc.)
  exact_or_proxy: exact (in principle)
  symbol: SOX
  source_owner: varies
  public_no_auth: false
  historical_daily_close_available: yes
  machine_readable_without_browser_scrape: yes
  redistribution_risk: medium
  terms_risk: medium
  implementation_complexity: low
  recommended_status: reject
  reason: "NikkeiMicroScope MVP does not introduce paid data
    sources, API keys, secrets, or tokens. AGENTS.md and the
    repository risk policy prohibit this. Rejected at the
    contract level."
```

### 3.7 Broker / exchange / FIX APIs

```yaml
- name: broker or exchange APIs
  exact_or_proxy: exact (in principle)
  symbol: SOX
  source_owner: broker / exchange
  public_no_auth: false
  historical_daily_close_available: varies
  machine_readable_without_browser_scrape: yes
  redistribution_risk: high
  terms_risk: high
  implementation_complexity: high
  recommended_status: reject
  reason: "AGENTS.md forbids broker SDKs, order placement, live
    trading, and live broker integration. Broker / exchange APIs
    may also require auth, cookies, and credentials. Rejected at
    the contract level."
```

## 4. Decision

```yaml
sox_source_decision:
  decision: defer_adapter
  selected_source: null
  selected_symbol: null
  proxy: false
  reason: no reviewed public no-auth exact SOX source has been
    confirmed yet
```

Concretely:

* No exact public no-auth source for the PHLX Semiconductor Sector
  Index has been confirmed.
* The two obvious proxy candidates (SOXX and SMH) are ETFs, not
  the SOX index. Adopting either as `semiconductor.sox` would be
  a silent mislabeling.
* FRED, the source used for the four existing public adapters,
  does not carry the SOX index.
* Paid sources, broker APIs, and unofficial scrapes are rejected
  for the reasons in §3.

## 5. Locked contract rules

Until this document is updated to a `preferred` or `acceptable`
outcome:

* No adapter may write `semiconductor.sox`.
* No adapter may write `semiconductor.sox_change_pct`.
* No ETF proxy may be labeled as exact SOX.
* No raw index data (SOX, SOXX, SMH, or otherwise) may be
  committed as a fixture, exported, or redistributed in
  `fixtures/`, `exports/`, or `reports/`.
* No broker, exchange, auth, cookie, or paid source may be
  introduced as a SOX / semiconductor source.
* The schema field name remains `semiconductor.sox`. Any future
  proxy implementation that is approved by a future PR **must**
  also rename the field (e.g. `semiconductor.proxy_etf`) or use
  an explicit proxy label in the model.

## 6. Future PR path (for reviewer reference only)

A future PR that wishes to add a SOX / semiconductor adapter
**must** update this document **before** writing
`semiconductor.sox`. That PR must, at minimum:

* State which exact public no-auth source it uses, with a
  concrete URL or CSV endpoint.
* Prove that the source is no-auth by citing the HTTP request it
  issues and confirming no `Authorization`, `Cookie`, API key,
  or `.env` reading.
* Add a test that asserts no raw downloaded data is committed to
  `fixtures/`, `exports/`, or `reports/`.
* Add the same network-safety tests as the four existing public
  adapters.
* Re-validate the merged `MarketContext` after overlay.
* Distinguish exact from proxy clearly in both the adapter code
  and the model.
* If the source has any copyright / licensing / redistribution
  guard (as for the FRED NASDAQ100 series in PR #10), include a
  §7-style copyright / redistribution guard in the adapter doc.
* Update §8.5 of `docs/data-adapter-contract.md` to reflect the
  new source.

## 7. Non-claims

This document explicitly does **not** claim:

* That the SOX adapter will be added in a specific PR.
* That SOXX or SMH are equivalent to SOX. They are not.
* That any free scrape of the SOX index is acceptable. It is
  not.
* That a paid source is acceptable. It is not.
* That any broker / exchange / auth / cookie path is acceptable.
  It is not.
* That the schema will be widened or renamed in this PR. It
  will not.

## 8. Reviewer checklist

- [ ] The decision in §4 is one of `defer_adapter`,
      `exact_source_selected`, or `proxy_selected`.
- [ ] The decision matches the preferred outcome (`defer_adapter`)
      unless there is strong evidence in §3 for a different
      outcome.
- [ ] §3 evaluates at least one exact index candidate and at
      least SOXX and SMH as proxies.
- [ ] §5 explicitly forbids the four forbidden patterns
      (writing `sox` / `sox_change_pct`; mislabeling an ETF as
      exact SOX; committing or exporting raw index data;
      introducing broker / auth / cookie / paid source).
- [ ] The tests in
      `tests/test_sox_source_selection_docs.py` enforce all of
      the above.
- [ ] No `nms/data/*sox*` adapter file is added.
- [ ] No live HTTP code is added.
- [ ] No new runtime dependency is added.
- [ ] No GitHub workflow file is changed.
