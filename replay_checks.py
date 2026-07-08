#!/usr/bin/env python3
"""
replay_checks.py — offline assertion suite for the Morning Brief.

Replays an archived morning (default: the newest archive) through the FULL
production pipeline via `python brief.py --replay`, then asserts the product
guarantees of the 2026-07-07 relevance overhaul against the regenerated
index.html + data/latest.json:

  1. no low_relevance story card in the rendered page
  2. no capped filler card in the rendered page, and no client section
     exceeds the per-category caps (config.CATEGORY_CAPS)
  3. sports junk (e.g. the LOLC cricket story) never renders under a client
  4. recurring time-series posts (daily CBSL rate etc.) are rolled up to at
     most one line, repeats suppressed
  5. the executive summary strip is present and populated
  6. every client has a section containing either new coverage or an
     explicit "No new coverage" line
  7. outlet boilerplate is stripped from rendered headlines

Exits 0 when everything holds, 1 otherwise.

Run:  python3 replay_checks.py [YYYY-MM-DD]
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from config import CLIENTS, CATEGORY_CAPS

FAILURES = []

def check(ok, label, detail=''):
    mark = 'ok' if ok else 'FAIL'
    print(f'  [{mark:4}] {label}' + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        FAILURES.append(label)

def rendered_dom(html):
    """The visible document — everything before the embedded JSON blobs."""
    return html.split('<script id="story-data"', 1)[0]

def client_sections(dom):
    """Split the DOM into {client_key: section_html}."""
    sections = {}
    marks = [(m.group(1), m.start())
             for m in re.finditer(r'<div class="section" id="sec-(\w+)"', dom)]
    for i, (key, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(dom)
        sections[key] = dom[start:end]
    return sections

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    dates = sorted(p.stem for p in Path('data/archive').glob('*.json'))
    if not dates:
        print('✗ no archives available to replay'); sys.exit(1)
    if date is None:
        date = dates[-1]

    print(f'Replaying {date} through brief.py --replay ...')
    r = subprocess.run([sys.executable, 'brief.py', '--replay', date],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        print('✗ replay run failed'); sys.exit(1)

    html = Path('index.html').read_text(encoding='utf-8')
    data = json.loads(Path('data/latest.json').read_text(encoding='utf-8'))
    stories = data.get('stories', [])
    dom = rendered_dom(html)
    sections = client_sections(dom)

    print(f'\nChecks against the regenerated brief ({len(stories)} stories in JSON):')

    # 1 ── low_relevance never renders (but stays in JSON for audit)
    check('data-cat="low_relevance"' not in dom,
          'no low_relevance card in the rendered page')
    n_lowrel = sum(1 for s in stories if s.get('category') == 'low_relevance')
    if n_lowrel:
        print(f'  [ok  ] {n_lowrel} low_relevance stories retained in latest.json for audit')
    else:
        print('  [skip] no low_relevance stories this day — nothing to audit')

    # 2 ── caps respected in the DOM; capped stories flagged in JSON only
    for c in CLIENTS:
        sec = sections.get(c['key'], '')
        for cat, cap in CATEGORY_CAPS.items():
            n = len(re.findall(rf'<div class="story"[^>]*data-cat="{cat}"', sec))
            check(n <= cap,
                  f'{c["label"]}: {cat} cards within cap',
                  f'{n} rendered > cap {cap}')
    for s in stories:
        if s.get('is_capped'):
            check(f'>{s["headline"]} <' not in dom.replace('&amp;', '&'),
                  f'capped story stays out of the page: {s["headline"][:60]}')

    # 3 ── sports junk never sits in a client section
    check('Bowlers star in LOLC' not in sections.get('mas', ''),
          'LOLC cricket story not rendered under MAS')
    check('Bowlers star in LOLC' not in dom,
          'LOLC cricket story not rendered anywhere')

    # 4 ── recurring time-series posts rolled up to at most one line
    repeats = [s for s in stories if s.get('is_series_repeat')]
    leaders = [s for s in stories if s.get('is_series_leader')]
    rate_posts = [s for s in stories
                  if re.search(r'\bcbsl rates?\b', s.get('headline', ''), re.I)]
    if rate_posts:
        n_rate_dom = len(re.findall(r'\bCBSL rates?\b', dom, re.I))
        check(n_rate_dom <= 1,
              'daily CBSL rate posts appear at most once on the page',
              f'{n_rate_dom} occurrences')
        check(len(rate_posts) == 1 or len(repeats) >= 1,
              'repeated rate posts are flagged is_series_repeat in JSON')
    for s in repeats:
        check(s['headline'] not in dom.replace('&amp;', '&'),
              f'series repeat suppressed: {s["headline"][:60]}')
    for s in leaders:
        check('class="series-line"' in dom,
              'series leaders render as one-line recurring updates')
        break

    # 5 ── executive summary present and populated
    n_exec = len(re.findall(r'<li class="exec-item">', dom))
    check('Executive Summary' in dom, 'executive summary strip present')
    check(n_exec >= 3, 'executive summary populated (>= 3 items)',
          f'only {n_exec} items')

    # 6 ── every client gets a section: new cards or explicit no-news line
    for c in CLIENTS:
        sec = sections.get(c['key'], '')
        check(bool(sec), f'{c["label"]}: section present')
        if not sec:
            continue
        fresh = sec.split('<div class="fresh-block">', 1)
        fresh = fresh[1] if len(fresh) > 1 else ''
        for stop in ('<div class="series-block">', '<details'):
            fresh = fresh.split(stop, 1)[0]
        has_new_cards = '<div class="story"' in fresh
        has_no_new_line = 'class="no-new"' in fresh
        check(has_new_cards != has_no_new_line,
              f'{c["label"]}: fresh block has new cards XOR explicit no-new line',
              f'cards={has_new_cards} no_new={has_no_new_line}')

    # 7 ── headline boilerplate stripped
    check('Print Edition' not in dom,
          'no "Print Edition" boilerplate in rendered page')
    check('| Daily Mirror' not in dom,
          'no "| Daily Mirror" boilerplate in rendered page')

    print()
    if FAILURES:
        print(f'✗ {len(FAILURES)} check(s) FAILED')
        sys.exit(1)
    print('✓ all checks passed')
    sys.exit(0)


if __name__ == '__main__':
    main()
