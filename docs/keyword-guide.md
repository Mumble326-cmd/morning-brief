# Keywords.json - Governance Guide

## Structure Overview

Each client object in `keywords.json` follows this structure:

```json
{
  "label": "Display name for reports",
  "sector": "Industry classification",
  "must_include": ["Essential terms that define this client"],
  "direct_mentions": ["Exact brand/product names"],
  "industry_watch": ["Competitor, regulatory, and sector context"],
  "exclude": ["Terms to ignore/filter out"],
  "priority_sources": ["Preferred news outlets for this client"]
}
```

## Field Definitions

### `label`
The display name in the brief output.

**Example:** `"HNB"`, `"Hayleys"`, `"MAS Holdings"`

---

### `sector`
Classification for internal organization. Helps group clients by industry.

**Values:**
- `Banking`
- `Diversified Conglomerate`
- `Apparel Manufacturing & Export`
- `Electric Vehicles`
- `Finance`
- `Real Estate & Development`

**Example:** `"sector": "Banking"`

---

### `must_include`
**Anchor terms** that must appear in a story for it to be relevant. This is the safety filter.

If a story doesn't contain at least one of these terms, it's rejected before matching against `direct_mentions` or `industry_watch`.

**Why?** Prevents false positives when acronyms or company names appear in unrelated contexts.

**Example for HNB:**
```json
"must_include": [
  "Sri Lanka",
  "HNB",
  "HNB PLC",
  "Hatton National Bank",
  "HNB Finance",
  "HNB Life",
  "HNB General Insurance",
  "HNB Investment Bank"
]
```

**Example for MIFL (highest risk):**
```json
"must_include": [
  "Sri Lanka",
  "Mahindra",
  "Ideal Finance"
]
```
This ensures we never match "MIFL football" or Michigan teams.

---

### `direct_mentions`
**Exact brand/product/subsidiary names** that are definitely client coverage when mentioned.

If a story mentions any of these, it's flagged as direct coverage. No second-guessing.

**Example for Hayleys:**
```json
"direct_mentions": [
  "Hayleys",
  "Hayleys PLC",
  "Hayleys Fabric",
  "Hayleys Mobility",
  "Hayleys Plantations",
  "Hayleys Advantis",
  "Hayleys Solar",
  "Hayleys Eco Solutions",
  "Hayleys Lifesciences",
  "Haycarb",
  "Talawakelle Tea Estates"
]
```

---

### `industry_watch`
**Context terms** that signal relevant sector/competitor/regulatory news.

These are secondary filters. A story matching `industry_watch` is useful to include because it provides competitive or regulatory context, but it's not direct client coverage.

**When to include a term:**
- It's a direct competitor (`Sampath Bank` for HNB)
- It's a regulatory body (`CBSL` for banking)
- It's a sector keyword (`apparel exports Sri Lanka`)
- It's a policy area (`EV policy Sri Lanka`)

**Example for BYD:**
```json
"industry_watch": [
  "electric vehicle Sri Lanka",
  "EV imports Sri Lanka",
  "vehicle import tax Sri Lanka",
  "NEV Sri Lanka",
  "charging stations Sri Lanka",
  "David Pieris Automobiles",
  "BAIC Sri Lanka",
  "GWM Sri Lanka",
  "MG Sri Lanka"
]
```

---

### `exclude`
**Terms to filter out** stories that match `direct_mentions` or `industry_watch`.

**When to add an exclusion:**
- A term causes too many false positives
- A term overlaps with unrelated topics
- A term pollutes results with sports/entertainment

**Example for MAS:**
```json
"exclude": [
  "sports",
  "cricket",
  "school",
  "tournament",
  "Brandix cricket",
  "MCA"
]
```

This prevents MAS apparel manufacturing stories from getting mixed with school uniform or cricket team coverage.

**Example for MIFL:**
```json
"exclude": [
  "MIFL football",
  "MIFL league",
  "MIFL sports",
  "Michigan",
  "India league"
]
```

---

### `priority_sources`
**News outlets** to prioritize when ranking or filtering results.

A story from Daily FT is more valuable than a story from a small online blog. This field tells the tool which outlets matter most.

**Values:** Use outlet names from `outlets.json`.

**Example for HNB:**
```json
"priority_sources": [
  "Daily FT",
  "Daily Mirror",
  "The Island",
  "Daily News",
  "Sunday Times",
  "EconomyNext",
  "Newswire",
  "LBO"
]
```

---

## Workflow: Adding New Keywords

### Step 1: Identify the Gap
- Run the brief
- Note missing stories
- Example: "HNB leasing stories aren't showing up"

### Step 2: Add to Appropriate Array

| Issue | Fix Array | Example |
|-------|-----------|---------|
| Missing direct coverage | `direct_mentions` | Add `"HNB leasing"` |
| Industry context missing | `industry_watch` | Add `"private sector credit"` |
| False positives from a term | `exclude` | Add `"unrelated acronym"` |
| Competitor context missing | `industry_watch` | Add `"Sampath Bank"` |

### Step 3: Test & Commit

```bash
# Make sure you're up to date
git pull --rebase origin main

# Edit keywords.json in VSCode
# Test locally if possible

# Commit with clear message
git add keywords.json
git commit -m "Add HNB leasing and pawning keywords"

# Push
git push

# Trigger GitHub Action
# Go to Actions → Daily Morning Brief → Run workflow
```

---

## Examples

### HNB: Banking Focus
- **Direct mentions:** All HNB products and subsidiaries
- **Industry watch:** Regulatory terms (CBSL, AWPLR), competitor banks, macroeconomic indicators
- **Exclude:** Unrelated acronyms, sports

### Hayleys: Conglomerate Ecosystem
- **Direct mentions:** All group companies and brands
- **Industry watch:** Sector terms (plantations, logistics, renewable), competitor conglomerates
- **Exclude:** Unrelated "Hayley" names

### MAS: Apparel Manufacturing
- **Direct mentions:** All MAS brands and subsidiaries
- **Industry watch:** Export trends, GSP+ status, tariff policy, competitor manufacturers
- **Exclude:** School uniforms, cricket teams, sports

### BYD: EV Market Entrant
- **Direct mentions:** Brand name, vehicle models, service touchpoints
- **Industry watch:** EV policy, charging infrastructure, competitor EVs
- **Exclude:** Global BYD news, China factory updates, Tesla comparisons

### MIFL: Acronym Risk
- **Direct mentions:** Full legal names only (avoid acronym)
- **Exclude:** Sports leagues, geographic matches (Michigan)

### Port City: Development Hub
- **Direct mentions:** All official names
- **Industry watch:** Investment climate, banking partnerships, real estate
- **Exclude:** Unrelated port operations

---

## Anti-Patterns to Avoid

### ❌ Too Broad
```json
"industry_watch": ["banking", "finance", "insurance"]
```
**Problem:** Every finance article appears. Not useful.

**Fix:** Be specific.
```json
"industry_watch": ["CBSL policy", "bank interest rates", "monetary policy"]
```

### ❌ Acronym Pollution
```json
"direct_mentions": ["MIFL"]
```
**Problem:** Matches "Michigan Football League", "Indian Film League", sports stories, etc.

**Fix:** Use full names in `direct_mentions`, restrict acronym in `must_include`.
```json
"must_include": ["Sri Lanka", "Mahindra", "Ideal Finance"],
"direct_mentions": ["Mahindra Ideal Finance", "Ideal Finance", "Mahindra Finance Sri Lanka"]
```

### ❌ Over-Excluding
```json
"exclude": ["cricket", "sports", "school", "tournament", "match", "team"]
```
**Problem:** You might exclude "Hayleys Sports Complex Development" which is relevant.

**Fix:** Exclude specific known false positives only.
```json
"exclude": ["Brandix cricket", "school apparel", "MAS cricket"]
```

### ❌ Mixing Sectors
```json
"direct_mentions": [
  "HNB",
  "Hayleys",
  "Port City Colombo"
]
```
**Problem:** This is not how it works. Each client has its own object.

**Correct Structure:**
```json
{
  "hnb": { ... },
  "hayleys": { ... },
  "pcc": { ... }
}
```

---

## Audit Checklist

Before committing keyword changes:

- [ ] Does `must_include` prevent false positives?
- [ ] Are all direct subsidiaries/products in `direct_mentions`?
- [ ] Does `industry_watch` add real context without noise?
- [ ] Are known false-positive patterns in `exclude`?
- [ ] Are `priority_sources` set to the outlets that matter most?
- [ ] Have I tested the changes locally?
- [ ] Does my commit message explain why the changes were made?

---

## Quick Reference

| Scenario | Array | Action |
|----------|-------|--------|
| "Add a new HNB subsidiary" | `direct_mentions` | Add `"HNB ServiceName"` |
| "Track a new competitor" | `industry_watch` | Add `"CompetitorName"` |
| "Stop false sports stories" | `exclude` | Add `"sport_keyword"` |
| "Add a regulatory term" | `industry_watch` | Add `"CBSL term"` |
| "Prefer Daily FT coverage" | `priority_sources` | Ensure `"Daily FT"` is listed |
| "Safety check for acronym" | `must_include` | Add context like `"Sri Lanka"` |

