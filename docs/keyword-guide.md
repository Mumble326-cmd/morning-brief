# Morning Brief — Keyword Tuning Guide

How keywords drive the brief, and how to tune them well. All examples are real,
taken from the current `keywords.json`.

---

## How keywords work

The pipeline in plain terms:

1. `brief.py` builds a Google News RSS query from a client's keyword terms.
2. Google News (Sri Lanka edition) returns up to ~20 matching articles.
3. The **SL_SIGNALS** gate removes articles with no Sri Lanka signal in the
   headline or snippet (`sri lanka`, `lanka`, `colombo`, `cbsl`, `ceylon`, `lkr`,
   `.lk`, and a few place names).
4. `classify_story()` assigns each surviving article a category.
5. Classified articles are deduplicated and placed into the brief.

**The five categories** (and the score each carries):

- **Mention (1.0)** — matched a `direct_mentions` term. The client itself is in
  the news.
- **Industry (0.7)** — matched an `industry_watch` term, **or** was pulled in by
  an `industry_watch` query even if no term re-appeared in the snippet (the
  *industry floor*).
- **Market Watch (0.5)** — pulled in by a `market_watch` query.
- **Risk Watch (0.8)** — pulled in by a `risk_watch` query, **or** a `risk_watch`
  term appears anywhere in the text.
- **Low Relevance (0.0)** — nothing matched, or an `exclude` term fired.

**Precedence** — `classify_story()` checks in this exact order and returns on the
first match:

```
1. exclude term            → low_relevance   (global gate, any fetch type)
2. market_watch / risk_watch fetch floor → that category
3. risk_watch term         → risk_watch      (checked BEFORE mentions)
4. direct_mentions term    → mention
5. industry_watch term     → industry
6. industry_watch fetch floor → industry
7. market_watch term       → market_watch
   (otherwise)             → low_relevance
```

Two consequences worth understanding:

- **exclude wins over everything.** A story matching both `"HNB"` and an HNB
  exclude term is demoted, not reported.
- **The industry floor (step 6)** means any story the `industry_watch` *query*
  returns becomes Industry, even if the exact term isn't echoed in the snippet.
  So the query terms are the real relevance gate — broaden too far and you pull
  noise into Industry.

---

## Term design rules

**Rule 1 — Short terms and named entities work; long phrases fail.**
A long fixed-word-order phrase rarely appears verbatim in a real headline.
- ❌ `"plantation sector Sri Lanka"` (never appears as-is)
- ✅ `"plantation sector"` or `"Aitken Spence"`

**Rule 2 — Short acronyms get automatic word-boundary matching.**
Terms of 4 characters or fewer are matched on word boundaries by the code, so
`BYD` won't hit "ABYDOS", `CSE` won't hit "SELECTED", `MAS` won't hit "THOMAS".
You don't need to guard against this yourself.

**Rule 3 — Avoid `"Sri Lanka"` inside terms.**
The tool already queries the Sri Lanka edition (`gl=LK`) and applies the
SL_SIGNALS gate. Adding `"Sri Lanka"` to a term just makes it longer and rarer.
- ❌ `"apparel exports Sri Lanka"`
- ✅ `"apparel exports"`

**Rule 4 — `query_context` is for globally ambiguous names only.**
`BYD` and `MIFL` have `"query_context": "Sri Lanka"`, which ANDs `"Sri Lanka"`
into every one of their queries so the feed isn't flooded with global BYD/MIFL
results. Do not remove it from those two. Don't add it to clients whose names are
already unambiguous (it makes their queries too narrow).

**Rule 5 — `exclude` terms are global and fire first.**
They demote a story before any positive match is considered. Powerful, so use
sparingly and specifically.

---

## Tuning a zero-coverage client

**Symptoms:** the client's section is missing, or shows only low-relevance items.

1. **Is the client wired up?** Run `py -3 brief.py` and watch the startup line.
   It warns if `config.py` `CLIENTS` and `keywords.json` have drifted apart.
2. **Are `direct_mentions` too narrow?** Use the exact company names and short
   acronyms actually used in Sri Lankan media.
3. **Are `industry_watch` terms long phrases?** Shorten them (Rule 1). This is
   the single most common cause — long `"… Sri Lanka"` phrases return nothing.
4. **Genuinely little press?** Some clients (e.g. MIFL — small-cap, ambiguous
   acronym) have near-zero automatic coverage. Use **manual clips** for the
   important stories instead of forcing broad terms.

---

## Tuning a noisy client

**Symptoms:** low-relevance flooding, or unrelated articles tagged as Mention.

- **Fix 1 — add `exclude` terms** for recurring noise, e.g. `"cricket"`, `"MCA"`,
  `"school"`, `"Brandix cricket"`.
- **Fix 2 — tighten `direct_mentions`** to full company names; drop bare short
  terms that pull unrelated stories.
- **Fix 3 — check `industry_watch` competitor names aren't too broad.** A name
  like `"CHEC"` can pull CHEC's projects in other countries; pair it with
  Sri Lanka-specific siblings or rely on the SL gate.

---

## market_watch vs industry_watch

- **industry_watch** — competitor names, sector bodies, export/import and policy
  terms.
- **market_watch** — stock-exchange names, index names, trading terms.

| Term | Goes in |
|------|---------|
| `"Aitken Spence"` | industry_watch |
| `"apparel exports"` | industry_watch |
| `"ASPI"` / `"CSE"` | market_watch |
| `"market turnover"` | market_watch |

Most clients have an empty `market_watch` today — only HNB tracks the bourse.
Add market terms only for listed clients whose share price / index movements you
actually want surfaced.

---

## When to use risk_watch

`risk_watch` is for negative or reputational signals: court orders,
investigations, customs disputes, military-ties allegations, regulatory action.

Real examples:
- BYD: `"BYD military ties"`, `"JKCG Letter of Credit"`, `"vehicle import surcharge Sri Lanka"`
- HNB: `"HNB fraud"`, `"HNB investigation"`

**Important:** `risk_watch` is checked **before** `direct_mentions`. A story
matching both `"BYD"` and `"BYD military ties"` is classified **Risk Watch, not
Mention** — intentionally, so negative stories are never buried as neutral
coverage.

---

## Adding a client: keyword checklist

When scaffolding a client with `py -3 new_client.py "Name" "Sector"`, fill the
blocks like this:

- **direct_mentions** — own brand + subsidiary names + short acronyms. ~6–10 terms.
- **industry_watch** — 2–4 named competitors plus 2–4 short sector / sector-body
  terms. Start narrow (Rule 1).
- **market_watch** — CSE ticker if listed, `"ASPI"`, sector index terms.
  Otherwise leave empty.
- **risk_watch** — leave empty until a specific risk pattern emerges.
- **exclude** — leave empty at first; add as real noise appears.
- **query_context** — set to `"Sri Lanka"` **only** if the brand name is
  globally ambiguous. Currently just BYD and MIFL.

---

## Reference: current client keyword counts

Run this to print the live counts:

```
py -3 -c "
import json
kw = json.load(open('keywords.json'))
for k, v in kw.items():
    print(f'{k:12} mentions={len(v.get(\"direct_mentions\",[]))} '
          f'industry={len(v.get(\"industry_watch\",[]))} '
          f'risk={len(v.get(\"risk_watch\",[]))} '
          f'exclude={len(v.get(\"exclude\",[]))}')"
```

Output (as of this writing):

```
hnb          mentions=17 industry=27 risk=9  exclude=6
hayleys      mentions=39 industry=20 risk=14 exclude=5
mas          mentions=22 industry=16 risk=12 exclude=6
byd          mentions=17 industry=16 risk=14 exclude=4
mifl         mentions=4  industry=24 risk=10 exclude=6
pcc          mentions=16 industry=17 risk=12 exclude=5
```

Note HNB is the only client with `market_watch` terms and broad `industry_watch`
(competitor banks + CBSL/rates), which is why its Industry coverage is the
healthiest. BYD carries the largest `risk_watch` set (the JKCG / import-surcharge
situation). MIFL has only 4 `direct_mentions` and relies on manual clips.

**2026-07-03 tuning pass (MAS / BYD / PCC):** BYD's entire `industry_watch` list
was 3-4 word phrases suffixed with `"Sri Lanka"` (e.g. `"vehicle import tax Sri
Lanka"`) — a straight Rule 1 + Rule 3 violation, and very likely why BYD's
industry coverage was near-zero (Google News quotes each OR term and matches it
as a literal substring; almost no real headline contains that exact 5-word
phrase). Shortened every BYD industry/market term to 1-3 words with no `"Sri
Lanka"` suffix, relying on the SL edition (`gl=LK`) + `SL_SIGNALS` gate for
relevance instead of baking it into the query. Same fix applied to MAS's
`"GSP+ Sri Lanka"` / `"EU trade Sri Lanka"` and PCC's `"SEZ Sri Lanka"` /
`"foreign investment Sri Lanka"` / `"financial centre Sri Lanka"` /
`"CHEC Sri Lanka"`. Added a handful of real, well-established named entities:
MAS gets `"Timex Garments"` (CSE-listed apparel exporter); PCC gets
`"Board of Investment"` and `"Urban Development Authority"` (the two government
bodies most likely to appear in Port City investment/land stories). Deliberately
did **not** add speculative EV competitor/model names for BYD (e.g. specific
current-year MG/Micro/Nissan Leaf distributor branding) — that needs your
on-the-ground knowledge of who's actually active in the Sri Lankan EV market
right now, not a guess. Add them via Keyword Studio if useful.
