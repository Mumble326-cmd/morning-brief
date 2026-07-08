#!/usr/bin/env python3
"""
utils.py — Helper functions for the Morning Brief generator
Includes story classification, duplicate detection, source ranking, and archive handling.
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import hashlib

SL_TZ = timezone(timedelta(hours=5, minutes=30))

# ── JSON Handling ──────────────────────────────────────────────────────────────

def load_json(path, default=None):
    """Load JSON file safely with default fallback."""
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return default if default is not None else {}

def save_json(path, data):
    """Save JSON file safely."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Text Normalization ──────────────────────────────────────────────────────────

def normalize_text(text):
    """Normalize text for comparison: lowercase, remove punctuation, collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_domain(url):
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc.lower()
    except:
        return ""

# ── Headline boilerplate ──────────────────────────────────────────────────────

# Site taglines that aggregators glue onto the front of the real headline,
# e.g. "Sri Lanka Latest Breaking News and Headlines - Print Edition Hayleys
# Mobility opens new Bellanthara workshop facility".
_BOILER_PREFIX_RE = re.compile(
    r'^(?:sri lanka(?:\'s)? )?latest breaking news(?: and headlines)?'
    r'\s*[-–—|:]?\s*(?:print edition)?\s*[-–—|:]?\s*',
    re.IGNORECASE)

# Words that identify a "| ..." segment as outlet branding rather than
# headline content ("... | Daily Mirror - Sri Lanka - newspaper"). Applied
# only to pipe-separated segments — real headlines almost never contain
# " | ", so this can afford broad terms like 'sri lanka'.
_BOILER_SEGMENT_WORDS = (
    'daily mirror', 'sri lanka', 'newspaper', 'print edition',
    'breaking news', 'latest news', 'news portal', '.lk',
)

def strip_headline_boilerplate(headline):
    """
    Remove outlet prefixes/suffixes an aggregator baked into the headline.
    Conservative by design: pipe segments are removed only when they look
    like outlet branding, and " - X" suffixes only for a fixed vocabulary,
    never when they read as headline content.
    """
    if not headline:
        return headline
    h = headline.strip()
    h = _BOILER_PREFIX_RE.sub('', h)
    # Drop everything from the first pipe segment that is outlet branding.
    parts = re.split(r'\s+\|\s+', h)
    if len(parts) > 1:
        for i in range(1, len(parts)):
            if any(w in parts[i].lower() for w in _BOILER_SEGMENT_WORDS):
                parts = parts[:i]
                break
        h = ' | '.join(parts)
    # Trailing " - Print Edition" style suffixes (fixed vocabulary only).
    h = re.sub(r'\s+[-–—]\s+(?:print edition|newspaper|e-?paper)\s*$', '', h,
               flags=re.IGNORECASE)
    return h.strip() or headline.strip()

# ── Source Ranking ────────────────────────────────────────────────────────────

def source_rank(domain, outlets_config):
    """
    Assign source rank (1-5) based on outlets.json configuration.
    1 = priority, 2 = accepted, 3 = international, 4 = aggregator, 5 = blocked
    """
    if not domain:
        return 4

    domain = domain.lower()

    if domain in outlets_config.get('priority_domains', []):
        return 1
    if domain in outlets_config.get('accepted_domains', []):
        return 2
    if domain in outlets_config.get('international_domains', []):
        return 3
    if domain in outlets_config.get('aggregator_domains', []):
        return 4
    if domain in outlets_config.get('blocked_domains', []):
        return 5
    return 4

def source_name_rank(source_name, outlets_config):
    """
    Rank by the outlet's display name (e.g. 'Daily FT') rather than its URL
    domain. Used for Google News RSS items whose domain is news.google.com —
    the RSS <source> tag gives the real outlet name even before redirect resolution.
    Returns 1 if name matches a priority outlet, 3 otherwise (unknown but named
    is still better than aggregator rank 4).
    """
    if not source_name:
        return 4
    s = source_name.lower()
    for name in outlets_config.get('priority_outlets', []):
        n = name.lower()
        if n in s or s in n:
            return 1
    for name in outlets_config.get('accepted_outlets', []):
        n = name.lower()
        if n in s or s in n:
            return 2
    return 3

def effective_source_rank(story, outlets_config):
    """
    Pick the best available rank for a story. If we have a real domain, use
    domain-based ranking. For unresolved news.google.com stories, fall back to
    name-based ranking so 'Daily FT' beats 'Unknown Aggregator' at cluster-primary
    selection time (which happens before URL resolution).
    """
    domain = extract_domain(story.get('url', ''))
    if domain and domain != 'news.google.com':
        return source_rank(domain, outlets_config)
    stored = story.get('source_rank')
    if stored is not None and domain != 'news.google.com':
        return stored
    return source_name_rank(story.get('source', ''), outlets_config)

# ── Story Classification ──────────────────────────────────────────────────────

def term_matches(term, text):
    """
    Test whether a keyword term occurs in text.

    Short terms (<= 4 chars) need word-boundary matching to avoid false
    positives — bare substring matching makes "BYD" hit "ABYDOS", "CSE" hit
    "SELECTED", "MAS" hit "THOMAS". Longer, multi-word terms are unambiguous
    enough that plain substring matching is both safe and cheaper.
    """
    t = term.lower()
    text = text.lower()
    if len(term) <= 4:
        return bool(re.search(r'\b' + re.escape(t) + r'\b', text))
    return t in text

def classify_story(story, client_config, outlets_config, fetch_type_hint=None,
                   global_exclude=()):
    """
    Classify a story based on keywords and rules.
    Returns: (category, relevance_score, matched_terms)
    Categories: 'mention', 'industry', 'market_watch', 'risk_watch', 'low_relevance'

    fetch_type_hint: If provided ('direct_mentions', 'industry_watch', 'market_watch', 'risk_watch'),
    uses it as primary classification hint but can override based on content.

    global_exclude: terms from config.GLOBAL_EXCLUDE that demote a story for
    every client (sports vocabulary etc.), checked alongside the client list.

    Order of precedence:
      1. exclude terms  → low_relevance (GLOBAL, any fetch_type)
      2. market/risk fetch floor (snippets rarely echo query terms)
      3. risk_watch     → a negative story must never be buried as a neutral
                          mention, so risk is checked before direct_mentions
                          (fixes "US adds BYD to military ties" → was Mention)
      4. direct_mentions
      5. industry_watch
      6. market_watch
    """
    headline = (story.get('headline') or '').lower()
    snippet = (story.get('snippet') or '').lower()
    text = headline + ' ' + snippet

    # ── 1. Global exclude gate — demotes ALL stories regardless of fetch_type ──
    # A "HNB cricket sponsorship" fetched by direct_mentions should not surface
    # as a Mention just because the brand name appears. GLOBAL_EXCLUDE catches
    # junk shared by every client ("Bowlers star in LOLC Holdings' five wicket
    # win"); the per-client exclude list handles client-specific noise.
    for term in list(global_exclude) + client_config.get('exclude', []):
        if term_matches(term, text):
            return 'low_relevance', 0.0, []

    # ── 2. market_watch / risk_watch fetch floor ──────────────────────────────
    # RSS snippets are usually just the headline repeated, so the query terms
    # rarely reappear in the text. Keep the fetched category as a floor.
    if fetch_type_hint in ('market_watch', 'risk_watch'):
        hint_terms = client_config.get(fetch_type_hint, [])
        matched_terms = [t for t in hint_terms if term_matches(t, text)]
        relevance_score = 0.5 if fetch_type_hint == 'market_watch' else 0.8
        return fetch_type_hint, relevance_score, matched_terms

    # ── 3. risk_watch (checked before mentions: negative news takes priority) ──
    for term in client_config.get('risk_watch', []):
        if term_matches(term, text):
            return 'risk_watch', 0.8, [term]

    # ── 4. direct_mentions ─────────────────────────────────────────────────────
    for term in client_config.get('direct_mentions', []):
        if term_matches(term, text):
            return 'mention', 1.0, [term]

    # ── 5. industry_watch ──────────────────────────────────────────────────────
    matched_industry = [t for t in client_config.get('industry_watch', []) if term_matches(t, text)]
    if matched_industry:
        return 'industry', 0.7, matched_industry

    # industry_watch fetch floor — sits BELOW risk + mention (unlike the
    # market/risk floor in section 2) so a sector story that actually names the
    # client or is negative still gets promoted. A story pulled in by the
    # industry query whose long phrase terms don't re-appear in the snippet
    # (e.g. "apparel exports Sri Lanka" vs a reordered real headline) would
    # otherwise drop to low_relevance — this keeps it as industry. NOTE: returns
    # the 'industry' category, not the 'industry_watch' fetch_type, because the
    # renderer/filters key off 'industry'.
    if fetch_type_hint == 'industry_watch':
        return 'industry', 0.7, matched_industry

    # ── 6. market_watch ────────────────────────────────────────────────────────
    for term in client_config.get('market_watch', []):
        if term_matches(term, text):
            return 'market_watch', 0.5, [term]

    return 'low_relevance', 0.0, []

# ── Compound relevance scoring ────────────────────────────────────────────────
# Replaces the coarse 1.0 / 0.7 / 0.0 relevance_score for ORDERING purposes.
# score = category weight × match strength × source quality × freshness,
# scaled to 0–100. relevance_score is kept on each story for backwards
# compatibility, but every sort in the brief runs off `score`.

CATEGORY_WEIGHTS = {
    'mention':       1.0,
    'risk_watch':    0.95,
    'industry':      0.5,
    'market_watch':  0.3,
    'low_relevance': 0.0,
}

SOURCE_WEIGHTS = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.5, 5: 0.0}

FRESHNESS_HALF_LIFE_H = 36.0   # score's freshness component halves every 36h
FRESHNESS_FLOOR = 0.12         # a 30-day-old story never decays below this

def match_strength(story):
    """
    How directly the matched keyword ties the story to the client:
      1.0  — a matched term appears in the headline (brand-in-headline)
      0.75 — matched terms appear only in the snippet
      0.5  — fetch-floor classification: the query pulled the story in but the
             term isn't echoed in the visible text (weakest possible link)
    """
    terms = story.get('matched_terms') or []
    if not terms:
        return 0.5
    headline = story.get('headline') or ''
    if any(term_matches(t, headline) for t in terms):
        return 1.0
    return 0.75

def compound_score(story, now_ms):
    """
    Blend category, match strength, source authority, and freshness into a
    single 0–100 ordering score. Manual clips are floored at 60 so curated
    content never sinks below automated filler.
    """
    cat_w = CATEGORY_WEIGHTS.get(story.get('category'), 0.0)
    if cat_w == 0.0:
        return 0.0
    src_w = SOURCE_WEIGHTS.get(story.get('source_rank', 4), 0.5)
    ts = story.get('ts') or 0
    if ts and now_ms > ts:
        age_h = (now_ms - ts) / 3600000.0
        fresh = max(FRESHNESS_FLOOR, 0.5 ** (age_h / FRESHNESS_HALF_LIFE_H))
    elif ts:
        fresh = 1.0
    else:
        fresh = 0.3   # unknown date: assume stale-ish rather than fresh
    score = 100.0 * cat_w * match_strength(story) \
        * (0.55 + 0.45 * src_w) * (0.25 + 0.75 * fresh)
    if story.get('is_manual'):
        score = max(score, 60.0)
    return round(score, 1)

# ── Recurring time-series rollup ──────────────────────────────────────────────
# Detects daily data-point posts (CBSL exchange rate, T-bill auctions, market
# close) and rolls each (client, series) group up to its newest item. The
# newest gets is_series_leader + series_size; earlier repeats get
# is_series_repeat and are dropped from the rendered page.

def detect_series_key(story, series_patterns):
    """Return the series key for a story, or None if it isn't a series post."""
    headline = (story.get('headline') or '').lower()
    for key, pattern in series_patterns:
        if re.search(pattern, headline):
            return key
    # Generic fallback: identical wording with only the numbers changed
    # ("CBSL Rates: USD selling rate unchanged at Rs. 341" day after day).
    # Handled by exact digit-normalised signature grouping in rollup_series.
    return None

def _digit_signature(headline):
    """Normalise a headline to a digits-stripped signature for series grouping."""
    t = normalize_for_dedup(headline or '')
    t = re.sub(r'\d+(?:\s+\d+)*', '#', t)
    return t

def rollup_series(stories, series_patterns):
    """
    Tag recurring time-series posts across a list of cluster-primary stories.
    Two detectors feed the same grouping:
      • pattern series — config.SERIES_PATTERNS regex on the headline
        (applies to every category: the patterns are explicit and curated)
      • signature series — ≥2 same-client stories whose headlines are
        identical once digits are removed (pure data-point reposts).
        Restricted to industry/market_watch: a client's own coverage often
        legitimately repeats a digits-only-different headline across outlets
        ("...PAT doubled" re-run day apart), and a Mention must never be
        demoted to a one-line rollup by that coincidence.
    Mutates stories in place; returns the number of suppressed repeats.
    """
    groups = {}
    sig_groups = {}
    for s in stories:
        if s.get('category') in ('low_relevance',) or s.get('is_manual'):
            continue
        key = detect_series_key(s, series_patterns)
        if key:
            groups.setdefault((s.get('client'), key), []).append(s)
        elif s.get('category') in ('industry', 'market_watch'):
            sig = _digit_signature(s.get('headline'))
            if sig and '#' in sig:
                sig_groups.setdefault((s.get('client'), sig), []).append(s)

    # Signature groups only count as a series with 2+ members.
    for (client, sig), members in sig_groups.items():
        if len(members) >= 2:
            groups[(client, 'sig:' + sig[:40])] = members

    suppressed = 0
    for (client, key), members in groups.items():
        members.sort(key=lambda s: s.get('ts', 0), reverse=True)
        leader = members[0]
        leader['series_key'] = key
        leader['is_series_leader'] = True
        leader['series_size'] = len(members)
        for repeat in members[1:]:
            repeat['series_key'] = key
            repeat['is_series_repeat'] = True
            suppressed += 1
    return suppressed

# ── Per-client category caps ──────────────────────────────────────────────────

def apply_category_caps(stories, caps, now_ms):
    """
    Enforce per-client caps on filler-prone categories (config.CATEGORY_CAPS).
    Only stories that would actually render compete for slots (low_relevance,
    series repeats, and series leaders are already out of the card flow).
    Best compound score wins; the overflow is tagged is_capped and kept in
    the JSON for audit. Mutates in place; returns the number capped.
    """
    buckets = {}
    for s in stories:
        if s.get('category') not in caps:
            continue
        if s.get('is_series_repeat') or s.get('is_series_leader') or s.get('is_manual'):
            continue
        buckets.setdefault((s.get('client'), s['category']), []).append(s)

    capped = 0
    for (client, category), members in buckets.items():
        cap = caps[category]
        if len(members) <= cap:
            continue
        members.sort(key=lambda s: (s.get('score', 0.0), s.get('ts', 0)), reverse=True)
        for s in members[cap:]:
            s['is_capped'] = True
            capped += 1
    return capped

# ── Duplicate Detection ────────────────────────────────────────────────────────

def normalize_for_dedup(title):
    """Normalize title for duplicate detection."""
    # Remove quotes, extra spaces, punctuation
    t = title.lower()
    t = re.sub(r'["\']', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

DEDUP_WINDOW_MS = 120 * 3600 * 1000  # 5 days — financial results spread across outlets over days

def _jaccard(title_a, title_b):
    """Token-level Jaccard similarity of two headlines. Returns a value in [0, 1]."""
    a = set(normalize_for_dedup(title_a).split())
    b = set(normalize_for_dedup(title_b).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def are_likely_duplicates(story_a, story_b):
    """
    Decide whether two stories are the same news item republished/reworded.

    Rules:
      • Same URL                                        → merge
      • Different client                                → never merge
      • Exact headline (after normalisation), any gap   → merge (wire copy and
        press releases get re-run across outlets days apart)
      • Jaccard >= 0.38 AND published within 5 days    → merge
      • Jaccard >= 0.38 but a timestamp is missing      → merge (can't gate on
        time we don't have; strong title match is enough)
      • Jaccard < 0.38                                  → do not merge
    """
    # Same (non-empty) URL = definite duplicate
    if story_a.get('url') and story_a.get('url') == story_b.get('url'):
        return True

    # Different client = not a duplicate
    if story_a.get('client') != story_b.get('client'):
        return False

    title_a = normalize_for_dedup(story_a.get('headline', ''))
    title_b = normalize_for_dedup(story_b.get('headline', ''))
    if not title_a or not title_b:
        return False

    # Fast path: identical normalised headline → merge regardless of time gap.
    if title_a == title_b:
        return True

    # Jaccard similarity on title tokens, gated by the dedup window.
    # 0.38 threshold: catches different outlets rewriting the same story with
    # substantially different headlines while avoiding unrelated-story false merges.
    if _jaccard(title_a, title_b) >= 0.38:
        ts_a = story_a.get('ts', 0)
        ts_b = story_b.get('ts', 0)
        if not ts_a or not ts_b:
            return True
        if abs(ts_a - ts_b) <= DEDUP_WINDOW_MS:
            return True

    return False

def choose_primary_story(members, outlets_config):
    """
    Select the best primary from a list of clustered member stories.

    Preference order:
      1. Manual clips always win (curated content)
      2. Best-ranked outlet — uses effective_source_rank() so a 'Daily FT'
         Google News item beats an unknown aggregator even before URL resolution
      3. Most recent publication
    """
    return sorted(
        members,
        key=lambda s: (
            0 if s.get('is_manual') else 1,
            effective_source_rank(s, outlets_config),
            -s.get('ts', 0),
        ),
    )[0]

def cluster_stories(stories, outlets_config=None):
    """
    Group duplicate/near-duplicate stories into clusters.
    Each cluster: {primary, members, also_covered_by, cluster_id}.

    The primary is chosen by source rank (via choose_primary_story), NOT simply
    the newest story — so the highest-quality outlet fronts the cluster while
    the rest become "also covered by" chips.
    """
    if not stories:
        return []
    outlets_config = outlets_config or {}

    # Anchor on newest-first so the comparison anchor is the freshest item.
    sorted_stories = sorted(stories, key=lambda s: s.get('ts', 0), reverse=True)

    clusters = []
    used_indices = set()

    for i, story_a in enumerate(sorted_stories):
        if i in used_indices:
            continue

        members = [story_a]
        for j in range(i + 1, len(sorted_stories)):
            if j in used_indices:
                continue
            story_b = sorted_stories[j]
            if are_likely_duplicates(story_a, story_b):
                members.append(story_b)
                used_indices.add(j)
        used_indices.add(i)

        # Pick the best-ranked member as the cluster face.
        primary = choose_primary_story(members, outlets_config)
        secondaries = [m for m in members if m is not primary]

        cluster = {
            'primary': primary,
            'members': members,
            'also_covered_by': [
                {
                    'source':   s.get('source'),
                    'url':      s.get('url'),
                    'domain':   extract_domain(s.get('url', '')),
                    'headline': s.get('headline'),
                    'date':     s.get('date'),
                    'ts':       s.get('ts', 0),
                }
                for s in secondaries
            ],
            'cluster_id': hashlib.md5(
                f"{primary['client']}{primary['headline']}".encode()
            ).hexdigest()[:12],
        }
        clusters.append(cluster)

    return clusters

# ── History (NEW badges, trend counts) ────────────────────────────────────────

def load_previous_story_keys(today_iso, archive_dir='data/archive'):
    """
    Load story URLs and cluster ids from the most recent archive BEFORE today.
    Used to mark stories as new-since-yesterday.
    Returns: (urls set, cluster_ids set, prev_date_iso or None)
    """
    try:
        dates = sorted(f[:-5] for f in os.listdir(archive_dir) if f.endswith('.json'))
    except OSError:
        return set(), set(), None
    prev_dates = [d for d in dates if d < today_iso]
    if not prev_dates:
        return set(), set(), None
    prev_date = prev_dates[-1]
    data = load_json(os.path.join(archive_dir, prev_date + '.json'), {})
    urls, cids = set(), set()
    for s in data.get('stories', []):
        if s.get('url'):
            urls.add(s['url'])
        if s.get('cluster_id'):
            cids.add(s['cluster_id'])
    return urls, cids, prev_date

def load_trend_counts(client_keys, today_iso, days=14, archive_dir='data/archive'):
    """
    Per-client story counts per archived day (excluding low_relevance),
    for up to `days` dates before today. Returns {date_iso: {client: count}}.
    """
    counts = {}
    try:
        dates = sorted(f[:-5] for f in os.listdir(archive_dir) if f.endswith('.json'))
    except OSError:
        return counts
    for d in [x for x in dates if x < today_iso][-days:]:
        data = load_json(os.path.join(archive_dir, d + '.json'), {})
        day = {k: 0 for k in client_keys}
        for s in data.get('stories', []):
            if s.get('category') == 'low_relevance':
                continue
            if s.get('client') in day:
                day[s['client']] += 1
        counts[d] = day
    return counts

# ── Archive Handling ──────────────────────────────────────────────────────────

def get_archive_path(date=None):
    """Get archive path for a given date (defaults to today)."""
    if date is None:
        date = datetime.now(SL_TZ).date()
    return f"data/archive/{date.isoformat()}.json"

def save_archive(stories, clusters, generated_at=None, write_dated=True,
                 latest_path='data/latest.json'):
    """
    Save current results to latest.json and dated archive.
    generated_at: run timestamp (defaults to now; replay passes the archived
    run's original timestamp so the regenerated brief matches that morning).
    write_dated: replay sets this False so a replayed run can never overwrite
    the historical archive files it reads its input from.
    latest_path: replay redirects this to its scratch directory so a replayed
    brief doesn't clobber the committed data/latest.json.
    """
    now = generated_at or datetime.now(timezone.utc)
    now_sl = now.astimezone(SL_TZ)
    
    # Clean stories for serialization (remove circular references)
    clean_stories = []
    for s in stories:
        clean_story = {k: v for k, v in s.items() if k != '_cluster_info'}
        clean_stories.append(clean_story)
    
    # Clean clusters for serialization
    clean_clusters = []
    for c in clusters:
        clean_cluster = {
            'cluster_id': c.get('cluster_id'),
            'primary_headline': c['primary'].get('headline', ''),
            'primary_source': c['primary'].get('source', ''),
            'also_covered_count': len(c.get('also_covered_by', []))
        }
        clean_clusters.append(clean_cluster)
    
    archive_data = {
        'generated_at': now.isoformat(),
        'generated_date': now_sl.strftime('%Y-%m-%d'),
        'generated_time': now_sl.strftime('%H:%M:%S SL'),
        'stories': clean_stories,
        'clusters_summary': clean_clusters,
        'total_stories': len(clean_stories),
        'total_clusters': len(clean_clusters),
    }
    
    # Save to latest.json
    save_json(latest_path, archive_data)

    # Save to dated archive
    if write_dated:
        archive_path = get_archive_path(now_sl.date())
        save_json(archive_path, archive_data)

# ── Archive Pruning ───────────────────────────────────────────────────────────

def prune_old_archives(keep_days=90, archive_dir='data/archive'):
    """Delete archive JSON files older than keep_days. Returns count deleted."""
    try:
        dates = sorted(f[:-5] for f in os.listdir(archive_dir) if f.endswith('.json'))
    except OSError:
        return 0
    to_delete = dates[:-keep_days] if len(dates) > keep_days else []
    deleted = 0
    for d in to_delete:
        try:
            os.remove(os.path.join(archive_dir, d + '.json'))
            deleted += 1
        except OSError:
            pass
    return deleted

# ── Validation ────────────────────────────────────────────────────────────────

def validate_no_private_contacts(html_content):
    """
    Check if HTML contains suspicious patterns for private contact info.
    Returns: (is_safe, messages)
    Note: Phone numbers in story content (from news articles) are acceptable.
    Only emails and structured contact patterns are failures.
    """
    is_safe = True
    messages = []
    
    # Check for email patterns (basic) — FAIL if found
    if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html_content):
        is_safe = False
        messages.append("✗ Email addresses found in HTML output (should not be stored)")
    
    # Check for contact footer or dedicated contact section (FAIL if found)
    if re.search(r'(contact|email:|phone:|call us|reach us|get in touch)', html_content, re.IGNORECASE):
        # Only fail if this looks like a structured contact section, not story content
        if re.search(r'<div[^>]*contact|<section[^>]*contact|contact-info|contact-section', html_content, re.IGNORECASE):
            is_safe = False
            messages.append("✗ Structured contact section found in HTML")
    
    # Warn about phone numbers if they appear to be structured (not in story text)
    # This is lenient — phone numbers in story snippets are okay
    phone_count = len(re.findall(r'(\+94|0\d{1,2})\s?\d{6,9}', html_content))
    if phone_count > 5:  # Many phone numbers suggests structured contact list
        messages.append(f"⚠ {phone_count} phone numbers detected (verify they're from news content, not contacts)")
    
    # Check for common journalist name patterns in structured context
    suspect_names = ['nisthar', 'cassim', 'journalist', 'editor', 'reporter']
    for name in suspect_names:
        if name.lower() in html_content.lower():
            if not any(word in html_content.lower() for word in ['the reporter', 'the editor', 'our journalist']):
                messages.append(f"ℹ Possible journalist reference '{name}' found (verify it's not sensitive)")
    
    return is_safe, messages
