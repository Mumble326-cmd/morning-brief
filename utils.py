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

# ── Source Ranking ────────────────────────────────────────────────────────────

def source_rank(domain, outlets_config):
    """
    Assign source rank (1-5) based on outlets.json configuration.
    1 = priority, 2 = accepted, 3 = international, 4 = aggregator, 5 = blocked
    """
    if not domain:
        return 4
    
    domain = domain.lower()
    
    # Check priority domains
    if domain in outlets_config.get('priority_domains', []):
        return 1
    
    # Check acceptable domains
    if domain in outlets_config.get('accepted_domains', []):
        return 2
    
    # Check international domains
    if domain in outlets_config.get('international_domains', []):
        return 3
    
    # Check low-priority/aggregator domains
    if domain in outlets_config.get('aggregator_domains', []):
        return 4
    
    # Check blocked domains
    if domain in outlets_config.get('blocked_domains', []):
        return 5
    
    # Default: unknown source is low priority
    return 4

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

def classify_story(story, client_config, outlets_config, fetch_type_hint=None):
    """
    Classify a story based on keywords and rules.
    Returns: (category, relevance_score, matched_terms)
    Categories: 'mention', 'industry', 'market_watch', 'risk_watch', 'low_relevance'

    fetch_type_hint: If provided ('direct_mentions', 'industry_watch', 'market_watch', 'risk_watch'),
    uses it as primary classification hint but can override based on content.

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
    # as a Mention just because the brand name appears.
    for term in client_config.get('exclude', []):
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

# ── Duplicate Detection ────────────────────────────────────────────────────────

def normalize_for_dedup(title):
    """Normalize title for duplicate detection."""
    # Remove quotes, extra spaces, punctuation
    t = title.lower()
    t = re.sub(r'["\']', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

DEDUP_WINDOW_MS = 72 * 3600 * 1000   # 72 hours

def _jaccard(title_a, title_b):
    """
    Token-level Jaccard similarity of two headlines. Threshold 0.5 per the
    academic / industry standard for news-title near-duplicate detection
    (USPTO patent 10783200; arxiv.org/abs/2410.01141; NewsCatcher API dedup
    docs). Returns a value in [0, 1].
    """
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
      • Jaccard >= 0.5 AND published within 72 hours    → merge
      • Jaccard >= 0.5 but a timestamp is missing        → merge (can't gate on
        time we don't have; strong title match is enough)
      • Jaccard < 0.5                                    → do not merge, even if
        the same outlet publishes twice
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

    # Jaccard similarity on title tokens, gated by a 72-hour window.
    if _jaccard(title_a, title_b) >= 0.5:
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
      1. Manual clips always win (curated, must stay the face of the cluster)
      2. Highest-ranked outlet — lowest source_rank (1 = priority SL outlet,
         4 = aggregator). Uses a story's stored source_rank if present, else
         derives it from the URL domain.
      3. Most recent publication (freshest framing of the same story)

    Fixes the original bug where the loop tracked best_rank/best_ts but never
    reassigned `best`, so it always returned the arbitrary first member.
    """
    def rank(s):
        r = s.get('source_rank')
        if r is None:
            r = source_rank(extract_domain(s.get('url', '')), outlets_config)
        return r

    return sorted(
        members,
        key=lambda s: (0 if s.get('is_manual') else 1, rank(s), -s.get('ts', 0)),
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

def save_archive(stories, clusters):
    """Save current results to latest.json and dated archive."""
    now = datetime.now(timezone.utc)
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
    save_json('data/latest.json', archive_data)
    
    # Save to dated archive
    archive_path = get_archive_path(now_sl.date())
    save_json(archive_path, archive_data)

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
