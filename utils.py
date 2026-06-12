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

def classify_story(story, client_config, outlets_config, fetch_type_hint=None):
    """
    Classify a story based on keywords and rules.
    Returns: (category, relevance_score, matched_terms)
    Categories: 'mention', 'industry', 'market_watch', 'risk_watch', 'low_relevance'
    
    fetch_type_hint: If provided ('direct_mentions', 'industry_watch', 'market_watch', 'risk_watch'),
    uses it as primary classification hint but can override based on content.
    """
    headline = (story.get('headline') or '').lower()
    snippet = (story.get('snippet') or '').lower()
    text = headline + ' ' + snippet
    
    category = 'low_relevance'
    relevance_score = 0.0
    matched_terms = []

    # Stories fetched via a market_watch or risk_watch query keep that category
    # as a floor: RSS snippets are usually just the headline repeated, so the
    # query terms rarely reappear in the text. Only an exclude term demotes them.
    if fetch_type_hint in ('market_watch', 'risk_watch'):
        exclude_terms = client_config.get('exclude', [])
        for term in exclude_terms:
            if term.lower() in text:
                return 'low_relevance', 0.0, []
        hint_terms = client_config.get(fetch_type_hint, [])
        matched_terms = [t for t in hint_terms if t.lower() in text]
        relevance_score = 0.5 if fetch_type_hint == 'market_watch' else 0.8
        return fetch_type_hint, relevance_score, matched_terms

    # ── Check direct_mentions (highest priority) ───────────────────────────────
    mention_terms = client_config.get('direct_mentions', [])
    for term in mention_terms:
        if term.lower() in text:
            matched_terms.append(term)
            category = 'mention'
            relevance_score = 1.0
            return category, relevance_score, matched_terms
    
    # ── Check industry_watch (if not a mention) ──────────────────────────────────
    industry_terms = client_config.get('industry_watch', [])
    for term in industry_terms:
        if term.lower() in text:
            matched_terms.append(term)
            category = 'industry'
            relevance_score = 0.7
            return category, relevance_score, matched_terms
    
    # ── Check market_watch (if not mention or industry) ───────────────────────────
    market_terms = client_config.get('market_watch', [])
    for term in market_terms:
        if term.lower() in text:
            matched_terms.append(term)
            category = 'market_watch'
            relevance_score = 0.5
            return category, relevance_score, matched_terms
    
    # ── Check risk_watch (independent) ──────────────────────────────────────────
    risk_terms = client_config.get('risk_watch', [])
    for term in risk_terms:
        if term.lower() in text:
            matched_terms.append(term)
            category = 'risk_watch'
            relevance_score = 0.8
            return category, relevance_score, matched_terms
    
    return category, relevance_score, matched_terms

# ── Duplicate Detection ────────────────────────────────────────────────────────

def normalize_for_dedup(title):
    """Normalize title for duplicate detection."""
    # Remove quotes, extra spaces, punctuation
    t = title.lower()
    t = re.sub(r'["\']', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def are_likely_duplicates(story_a, story_b, threshold=0.7):
    """
    Check if two stories are likely duplicates/near-duplicates.
    Uses title similarity, domain, and date proximity.
    """
    # Same URL = definite duplicate
    if story_a.get('url') == story_b.get('url'):
        return True
    
    # Same domain and similar title and similar date = likely duplicate
    domain_a = extract_domain(story_a.get('url', ''))
    domain_b = extract_domain(story_b.get('url', ''))
    
    # Different client = not a duplicate
    if story_a.get('client') != story_b.get('client'):
        return False
    
    # Normalize titles for comparison
    title_a = normalize_for_dedup(story_a.get('headline', ''))
    title_b = normalize_for_dedup(story_b.get('headline', ''))
    
    # Simple word overlap check
    words_a = set(title_a.split())
    words_b = set(title_b.split())
    
    if not words_a or not words_b:
        return False
    
    # Calculate overlap percentage
    common_words = words_a & words_b
    overlap = len(common_words) / min(len(words_a), len(words_b))
    
    # If overlap is high, check date proximity
    if overlap >= threshold:
        ts_a = story_a.get('ts', 0)
        ts_b = story_b.get('ts', 0)
        # If within 2 hours, likely duplicates
        if abs(ts_a - ts_b) < 7200000:  # 2 hours in ms
            return True
    
    return False

def cluster_stories(stories):
    """
    Group duplicate/near-duplicate stories into clusters.
    Returns list of clusters: each cluster is {primary_story, secondary_stories, cluster_id}
    """
    if not stories:
        return []
    
    # Sort by timestamp descending (newest first)
    sorted_stories = sorted(stories, key=lambda s: s.get('ts', 0), reverse=True)
    
    clusters = []
    used_indices = set()
    
    for i, story_a in enumerate(sorted_stories):
        if i in used_indices:
            continue
        
        cluster = {
            'primary': story_a,
            'also_covered_by': [],
            'cluster_id': hashlib.md5(f"{story_a['client']}{story_a['headline']}".encode()).hexdigest()[:12]
        }
        
        # Find other stories in this cluster
        for j in range(i + 1, len(sorted_stories)):
            if j in used_indices:
                continue
            
            story_b = sorted_stories[j]
            if are_likely_duplicates(story_a, story_b):
                cluster['also_covered_by'].append({
                    'source': story_b.get('source'),
                    'url': story_b.get('url'),
                    'domain': extract_domain(story_b.get('url', ''))
                })
                used_indices.add(j)
        
        clusters.append(cluster)
        used_indices.add(i)
    
    return clusters

def choose_primary_story(cluster, outlets_config):
    """
    Select the best primary story from a cluster based on source rank.
    Higher rank preference: rank 1 > 2 > 3 > 4 > 5
    If same rank, choose earliest publication date.
    """
    primary = cluster['primary']
    primary_domain = extract_domain(primary.get('url', ''))
    primary_rank = source_rank(primary_domain, outlets_config)
    primary_ts = primary.get('ts', 0)
    
    best = primary
    best_rank = primary_rank
    best_ts = primary_ts
    
    # Check secondary sources
    for secondary in cluster.get('also_covered_by', []):
        sec_rank = source_rank(secondary.get('domain', ''), outlets_config)
        sec_ts = 0  # We don't have timestamp for secondary in this format
        
        # Prefer higher rank (lower number), then earlier date
        if sec_rank < best_rank or (sec_rank == best_rank and sec_ts < best_ts):
            # Update primary if secondary is better
            best_rank = sec_rank
            best_ts = sec_ts
    
    return best

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
