# Morning Brief - Changelog

## 2026-06-11

### Major Updates

#### Keywords Structure Overhaul
- Migrated from basic `mentions`/`industry` to comprehensive keyword governance model
- Each client now has: `sector`, `must_include`, `direct_mentions`, `industry_watch`, `exclude`, `priority_sources`
- This enables stricter filtering and cleaner reporting

#### HNB Expansion
- Added subsidiaries: HNB General Insurance, HNB Investment Bank, HNB Securities, HNB Stockbrokers
- Added financial products: HNB SOLO, HNB MOMO, HNB leasing, HNB pawning, HNB SME, HNB digital banking
- Added regulatory terms: AWPLR, SLFR, SDFR, CRIB, NPL, credit growth
- Added competitor banks for industry context: People's Bank, DFCC Bank
- Reason: Google News missed subsidiary coverage; now properly tracks banking sector context

#### Hayleys Expansion
- Added all major subsidiaries: Hayleys Fentons, Aventura, Consumer, Free Zone, Lifecode, Agriculture, Electronics
- Added related entities: Kelani Valley Plantations, Dipped Products, Logiwiz, Unisyst
- Expanded industry watch with sector-specific terms: tea estates, rubber exports, activated carbon, logistics
- Reason: Better coverage of conglomerate ecosystem; reduce noise from unrelated "Hayley" stories

#### MAS Expansion
- Overhauled mentions with all brands: MAS Kreeda, Bodyline, Silueta, Fabric Park, Twinery, Linea Aqua, etc.
- Added specific exclusions: "Brandix cricket", "school apparel" to eliminate sports/school noise
- Expanded industry with GSP+ tariff tracking, US tariff implications
- Reason: Sports/school coverage was polluting results; now targets manufacturing/export focus

#### BYD Expansion
- Added vehicle models: Atto 3, Dolphin, Seal
- Added service touchpoints: aftersales, service centre, showroom, charging
- Added Denza brand for premium EV track
- Added Motor Traffic policy terms
- Reason: More precise vehicle launch/service/policy coverage

#### MIFL Tightening
- Restricted to only Mahindra Ideal Finance mentions (avoid sports league pollution)
- Added strict exclusions: "MIFL football", "MIFL league", "MIFL sports", "Michigan", "India league"
- Expanded finance company landscape
- Reason: MIFL acronym is high-risk for false matches

#### Port City Colombo Enhancement
- Added SEZ governance terms: Port City Economic Commission, CCEC
- Added banking partnership focus: Sampath Bank Port City, Commercial Bank Port City
- Added financial centre positioning
- Reason: Track investment inflows and banking partnerships separately from general real estate

### Governance Updates
- Created `outlets.json` to govern media sources and domain whitelist
- Created `docs/` folder structure for documentation
- Created `data/` folder with `archive/` for historical tracking
- Created `.github/workflows/` for CI/CD organization

### Next Steps
1. Update `brief.py` to read from new keyword structure
2. Add archive output: `data/latest.json` and `data/archive/YYYY-MM-DD.json`
3. Add duplicate story grouping logic
4. Build client report view with date range and story filtering
5. Add PDF export capability

### Breaking Changes
- Keyword file structure changed: `mentions` → `direct_mentions`, `industry` → `industry_watch`
- **Required:** Update `brief.py` to parse new structure
