# Morning Brief - Manual

## What This Tool Does

The Morning Brief automatically scans news articles from ~15 Sri Lankan news outlets and groups coverage by client company (HNB, Hayleys, MAS, BYD, MIFL, Port City Colombo).

Every day:
1. Google News is searched for keywords related to each client
2. Results are categorized as **direct mentions** (client in headline) or **industry context** (sector/competitor news)
3. An HTML brief is generated and published to GitHub Pages
4. Archive is stored for historical comparison

---

## Project Structure

```
morning-brief/
├─ brief.py              # Main script (runs daily via GitHub Action)
├─ config.py             # Configuration (API keys, parameters)
├─ keywords.json         # Client keyword definitions (EDIT THIS)
├─ outlets.json          # Approved news outlets and domains
├─ index.html            # Generated output page
├─ README.md             # Project overview
│
├─ data/                 # Output archive
│  ├─ latest.json        # Latest results
│  └─ archive/           # Historical snapshots (YYYY-MM-DD.json)
│
├─ docs/                 # Documentation
│  ├─ manual.md          # This file
│  ├─ keyword-guide.md   # How to edit keywords.json
│  └─ changelog.md       # Version history
│
└─ .github/workflows/    # GitHub Actions CI/CD
   └─ daily-brief.yml    # Automation trigger
```

---

## Quick Start

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the brief generator
python brief.py

# Output appears in index.html
```

### Edit Keywords

1. Open `keywords.json` in VSCode
2. Refer to `docs/keyword-guide.md` for structure
3. Make changes (add subsidiaries, adjust filters, etc.)
4. Commit and push:

```bash
git pull --rebase origin main
git add keywords.json
git commit -m "Reason for the change"
git push
```

5. GitHub Action runs automatically; check **Actions** tab for results

### View Results

- **Latest brief:** https://yourGitHubPages URL (set in repo settings)
- **Archive:** `data/archive/` folder in repo
- **Raw JSON:** `data/latest.json`

---

## Client Keyword Management

Each client is defined in `keywords.json` with these fields:

| Field | Purpose |
|-------|---------|
| `label` | Display name in brief |
| `sector` | Industry classification |
| `must_include` | Safety filter (story must contain one) |
| `direct_mentions` | Exact brand/subsidiary names |
| `industry_watch` | Competitor/regulatory/sector context |
| `exclude` | False-positive filters |
| `priority_sources` | Preferred news outlets |

**Full guide:** See `docs/keyword-guide.md`

---

## Current Clients

### HNB (Hatton National Bank)
**Sector:** Banking
- Tracks HNB and all subsidiaries (Life, Finance, General Insurance, Investment Bank, Securities, Stockbrokers, Assurance)
- Industry context: CBSL, monetary policy, competing banks
- Excludes: sports, horse racing

### Hayleys
**Sector:** Diversified Conglomerate
- Tracks Hayleys PLC and all subsidiaries (Fabric, Mobility, Plantations, Advantis, Solar, Eco Solutions, Lifesciences, Haycarb, etc.)
- Industry context: plantation sector, competing conglomerates, renewables
- Excludes: sports, cricket

### MAS
**Sector:** Apparel Manufacturing & Export
- Tracks MAS Holdings and all brands (Intimates, Active, Kreeda, Bodyline, Twinery, etc.)
- Industry context: apparel exports, GSP+ status, tariff policy, competing manufacturers
- Excludes: school uniforms, sports, cricket

### BYD
**Sector:** Electric Vehicles
- Tracks BYD Sri Lanka and vehicle models (Atto 3, Dolphin, Seal)
- Industry context: EV policy, charging infrastructure, competing EVs
- Excludes: global BYD news, China factory updates, Tesla comparisons

### MIFL
**Sector:** Finance
- Tracks Mahindra Ideal Finance only (strict acronym filtering)
- Industry context: licensed finance companies, NBFIs, leasing landscape
- Excludes: sports leagues, geographic matches

### Port City Colombo
**Sector:** Real Estate & Development
- Tracks Port City and all official names (Colombo Port City, CHEC Port City, SEZ)
- Industry context: foreign investment, banking partnerships, real estate
- Excludes: port operations, unrelated commerce

---

## GitHub Action Workflow

File: `.github/workflows/daily-brief.yml`

**Trigger:** Daily at a set time (usually 06:00 AM)

**What it does:**
1. Pulls latest code from main branch
2. Runs `python brief.py`
3. Generates `data/latest.json` and archives to `data/archive/YYYY-MM-DD.json`
4. Commits and pushes results
5. Publishes to GitHub Pages (if enabled in repo settings)

**To manually trigger:**
- GitHub → Actions → Daily Morning Brief → Run workflow

---

## Troubleshooting

### Missing Stories

**Problem:** A known HNB story isn't appearing.

**Diagnosis:**
1. Check if the outlet is in `outlets.json` → `allowed_domains`
2. Check if keywords match in `keywords.json` → `direct_mentions` or `industry_watch`
3. Check if the story is being excluded in `exclude` array
4. Run `python brief.py` locally with debug output

**Fix:**
- Add missing keywords to `direct_mentions` or `industry_watch`
- Add outlet to `outlets.json` if it's a valid source
- Remove the keyword from `exclude` if it's a false positive

### Too Many False Positives

**Problem:** MAS apparel stories mixed with school uniform articles.

**Diagnosis:**
1. Check `keywords.json` → `exclude` array
2. Verify `must_include` logic

**Fix:**
- Add specific false-positive patterns to `exclude`, e.g., `"school apparel"`, `"Brandix cricket"`
- Avoid broad exclusions like `"school"` (might exclude "school factory expansion")

### Acronym Pollution

**Problem:** MIFL stories mixed with Michigan Football or Indian Film League.

**Diagnosis:**
- `must_include` array is not strict enough
- `direct_mentions` includes bare `"MIFL"` without context

**Fix:**
- Keep `direct_mentions` to full names only: `"Mahindra Ideal Finance"`
- Ensure `must_include` has context anchors: `["Sri Lanka", "Mahindra", "Ideal Finance"]`
- Add exclusions: `["MIFL football", "MIFL league", "Michigan", "India league"]`

### GitHub Action Failed

**Problem:** Workflow shows red X in Actions tab.

**Steps:**
1. Click on the failed run
2. Expand the job to see error log
3. Common issues:
   - `keywords.json` is malformed JSON → validate syntax
   - Missing dependency → update `requirements.txt`
   - API rate limit → wait or reduce query frequency
4. Fix locally, commit, and re-run

---

## Data Export & Archiving

### Latest Results
`data/latest.json` contains today's stories with metadata:
- headline
- url
- source
- publish date
- matched keywords
- category (direct_mention / industry_watch)

### Historical Archive
`data/archive/2026-06-11.json` stores daily snapshots.

**Use cases:**
- "Which outlet covered HNB most in May?"
- "Did BYD coverage spike after the new model launch?"
- "How many Port City stories in Q1?"

---

## Media Contact Safety

**⚠️ IMPORTANT:** Do NOT store journalist names, email addresses, or phone numbers in this public GitHub repo.

**Current policy:**
- Brief output shows only: `Outlet Name · Date · Link`
- No contact details are hardcoded in public files
- Keep media contact lists in private files (Excel, OneNote, CRM)

**If adding contact data later:**
- Store in `media_contacts.json` (add to `.gitignore`)
- Or create a private report generator for internal use only

---

## Next Improvements

### Short Term
1. ✅ Expanded keyword coverage (HNB subsidiaries, BYD models, etc.)
2. ✅ Governance structure (must_include, direct_mentions, industry_watch)
3. ⏳ Update `brief.py` to parse new keyword structure
4. ⏳ Archive output capability

### Medium Term
5. ⏳ Duplicate story grouping
6. ⏳ Client report view with date range filtering
7. ⏳ Outlet performance tracking

### Long Term
8. ⏳ PDF export
9. ⏳ Negative mention flagging
10. ⏳ Trend analysis dashboard

---

## Support

For issues or questions:
1. Check `docs/changelog.md` for recent updates
2. Review `docs/keyword-guide.md` for keyword structure
3. Check GitHub Issues (if using)
4. Contact project maintainer

---

**Last Updated:** 2026-06-11
**Maintainer:** Mumble326
**Repository:** https://github.com/Mumble326-cmd/morning-brief
