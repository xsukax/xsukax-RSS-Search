#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universal RSS Keyword Searcher (v1.3, Apple-style HTML)
------------------------------------------------------

- Country-agnostic: reads all feed URLs from a plain text file (default: feeds.txt)
- One URL per line; '#' starts a comment; blank lines ignored
- Prompts for keywords (Arabic or English supported via normalization)
- Lets you search in title, description, or both; match ANY or ALL keywords
- Generates an Apple-like HTML page
- Output filename includes the FIRST keyword + current date & time

Dependencies:
    pip install feedparser requests
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import html
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import feedparser  # type: ignore
import requests    # type: ignore

UA = "Mozilla/5.0 (compatible; UniversalRSSBot/1.3; +https://example.local)"
DEFAULT_TIMEOUT = 12

# ----------------------- Text & Match Utilities ----------------------------- #

def normalize(text: str) -> str:
    """Unicode-normalize and lightly canonicalize Arabic & English for matching."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = t.replace("ـ", "")  # Arabic tatweel
    # Strip Arabic diacritics U+064B..U+065F and U+0670
    t = "".join(ch for ch in t if not (0x064B <= ord(ch) <= 0x065F or ord(ch) == 0x0670))
    # Unify alef forms; map alif maqsura to yaa
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return t

def parse_keywords(raw: str) -> List[str]:
    """Split keywords by comma or newline; trim and normalize."""
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    parts = [p for p in parts if p]
    return [normalize(p) for p in parts]

def matches(text: str, keywords: List[str], mode: str) -> bool:
    """Return True if text matches keywords under 'any' or 'all' mode."""
    nt = normalize(text)
    if not keywords:
        return False
    hits = [(kw in nt) for kw in keywords]
    return any(hits) if mode == "any" else all(hits)

def entry_datetime(e: Dict[str, Any]) -> float:
    """Extract epoch seconds from a feed entry where available."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        dt = e.get(key)
        if dt:
            try:
                return time.mktime(dt)
            except Exception:
                pass
    return 0.0

def slugify_for_filename(s: str, fallback: str = "results") -> str:
    """
    Make a filesystem-friendly slug. Keep Unicode letters/digits, replace spaces
    with underscores, and strip other unsafe characters.
    """
    if not s:
        return fallback
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^0-9A-Za-z\u0600-\u06FF_\-\.]+", "", s)  # allow Arabic range
    s = s.strip("._-")
    return s or fallback

# -------------------------- Feeds I/O --------------------------------------- #

def load_feeds_from_txt(path: str) -> List[str]:
    """
    Read 'feeds.txt' line by line. Ignore blanks and lines starting with '#'. 
    """
    feeds: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            ln = line.strip()
            if not ln or ln.startswith("#"):
                continue
            feeds.append(ln)
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for u in feeds:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return uniq

# -------------------------- Networking & Parsing ---------------------------- #

def safe_entries(parsed: Any) -> List[Dict[str, Any]]:
    """Safely obtain entries from a feedparser object or dict."""
    try:
        if isinstance(parsed, dict):
            ent = parsed.get("entries", [])
        else:
            ent = getattr(parsed, "entries", [])
    except Exception:
        ent = []
    return ent if isinstance(ent, list) else []

def fetch_and_parse(url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[str, Any, Optional[Exception]]:
    """Fetch a feed and return (url, parsed, error)."""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        return url, parsed, None
    except Exception as exc:
        return url, {"entries": []}, exc

def field_text(entry: Dict[str, Any], which: str) -> str:
    """Select text to search: title / description / both."""
    title = entry.get("title") or ""
    summary = entry.get("summary") or entry.get("description") or ""
    if which == "title":
        return title
    if which == "description":
        return summary
    return f"{title}\n{summary}"

# -------------------------- HTML Rendering ---------------------------------- #

def render_html(
    results: List[Dict[str, Any]],
    keywords: List[str],
    search_field: str,
    mode: str,
    generated_at: datetime,
    total_feeds: int,
    failed_feeds: List[Tuple[str, Optional[Exception]]],
) -> str:
    """
    Modern Apple-like design with improved spacing, typography, and visual hierarchy.
    """
    kw_display = ", ".join(html.escape(k) for k in keywords) if keywords else "—"
    fail_notes = ""
    if failed_feeds:
        fail_notes = " / ".join(f"{html.escape(url)}" for (url, _err) in failed_feeds)

    items_html = []
    for r in results:
        link = html.escape(r["link"] or "#")
        title = html.escape(r["title"] or "(no title)")
        src = html.escape(r.get("source", ""))  # host
        date_str = r.get("date_str", "")
        descr = r.get("summary", "")
        excerpt = html.escape(descr[:240] + ("…" if len(descr) > 240 else "")) if descr else ""
        items_html.append(f"""
        <article class="card">
          <a class="title" href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
          <div class="meta">
            {f'<span class="source">{src}</span><span class="dot">•</span>' if src else ''}
            <time class="date">{date_str}</time>
          </div>
          {f'<p class="excerpt">{excerpt}</p>' if excerpt else ''}
        </article>
        """)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>xsukax RSS Search Results</title>
<style>
:root {{ --bg: #fafafa; --text: #1d1d1f; --muted: #86868b; --card: #ffffff; --border: #d2d2d7; --shadow: 0 2px 16px rgba(0,0,0,0.08); --accent: #007aff; --success: #30d158; --warning: #ff9500; --error: #ff3b30; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #000000; --text: #f5f5f7; --muted: #a1a1a6; --card: #1c1c1e; --border: #38383a; --shadow: 0 2px 16px rgba(0,0,0,0.24); --accent: #0a84ff; --success: #32d74b; --warning: #ff9f0a; --error: #ff453a; }} }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font: 17px/1.47 -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }}
.container {{ max-width: 1024px; margin: 0 auto; padding: 40px 24px; }}
header {{ margin-bottom: 48px; text-align: center; }}
h1 {{ font-size: clamp(32px, 5vw, 48px); font-weight: 700; letter-spacing: -0.5px; margin-bottom: 16px; background: linear-gradient(135deg, var(--text) 0%, var(--muted) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.subtitle {{ color: var(--muted); font-size: 18px; font-weight: 400; margin-bottom: 24px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; align-items: center; }}
.stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 20px; font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 8px; }}
.stat-icon {{ width: 12px; height: 12px; border-radius: 50%; }}
.stat-icon.feeds {{ background: var(--accent); }}
.stat-icon.results {{ background: var(--success); }}
.stat-icon.field {{ background: var(--warning); }}
.stat-icon.mode {{ background: var(--error); }}
.keywords {{ background: linear-gradient(135deg, var(--accent), #5856d6); color: white; border: none; }}
.error-banner {{ background: rgba(255, 59, 48, 0.1); border: 1px solid rgba(255, 59, 48, 0.2); border-radius: 16px; padding: 20px; margin: 24px 0; color: var(--error); font-size: 14px; }}
.grid {{ display: grid; gap: 20px; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 24px; box-shadow: var(--shadow); transition: all 0.2s ease; position: relative; overflow: hidden; }}
.card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--accent), #5856d6); }}
.card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,0.12); }}
@media (prefers-color-scheme: dark) {{ .card:hover {{ box-shadow: 0 8px 32px rgba(0,0,0,0.4); }} }}
.title {{ display: block; color: var(--text); text-decoration: none; font-weight: 600; font-size: 20px; line-height: 1.3; margin-bottom: 12px; }}
.title:hover {{ color: var(--accent); }}
.meta {{ display: flex; align-items: center; gap: 12px; color: var(--muted); font-size: 14px; margin-bottom: 16px; }}
.source {{ font-weight: 500; color: var(--accent); }}
.dot {{ opacity: 0.6; }}
.date {{ font-variant-numeric: tabular-nums; }}
.excerpt {{ color: var(--muted); font-size: 16px; line-height: 1.5; }}
.empty {{ text-align: center; padding: 80px 24px; color: var(--muted); }}
.empty-icon {{ font-size: 48px; margin-bottom: 16px; }}
footer {{ margin-top: 64px; padding-top: 32px; border-top: 1px solid var(--border); text-align: center; color: var(--muted); font-size: 14px; }}
footer code {{ background: rgba(142, 142, 147, 0.12); padding: 4px 8px; border-radius: 6px; font-family: 'SF Mono', Monaco, Inconsolata, 'Roboto Mono', Consolas, 'Courier New', monospace; }}
@media (max-width: 768px) {{ .container {{ padding: 24px 16px; }} .stats {{ flex-direction: column; align-items: stretch; }} .stat {{ justify-content: center; }} h1 {{ font-size: 32px; }} }}
</style>
</head>
<body>
  <div class="container">
    <header>
      <h1>xsukax RSS Search Results</h1>
      <p class="subtitle">
        Generated on {generated_at.strftime('%B %d, %Y at %I:%M %p')}
      </p>
      <div class="stats">
        <div class="stat">
          <div class="stat-icon feeds"></div>
          Feeds: {total_feeds}
        </div>
        <div class="stat">
          <div class="stat-icon results"></div>
          Results: {len(results)}
        </div>
        <div class="stat">
          <div class="stat-icon field"></div>
          Field: {html.escape(search_field)}
        </div>
        <div class="stat">
          <div class="stat-icon mode"></div>
          Mode: {html.escape(mode)}
        </div>
        <div class="stat keywords">
          Keywords: {kw_display}
        </div>
      </div>
      {f'<div class="error-banner">⚠️ Some feeds failed or were skipped: {html.escape(fail_notes)}</div>' if failed_feeds else ''}
    </header>
    <main class="grid">
      {"".join(items_html) if items_html else '<div class="empty"><div class="empty-icon">🔍</div><h3>No matches found</h3><p>Try different keywords or search fields.</p></div>'}
    </main>
    <footer>
      <p>Generated by <code>xsukax_rss_search.py</code></p>
      <p>Edit <code>feeds.txt</code> to add or remove RSS feeds</p>
    </footer>
  </div>
</body>
</html>"""
    return html_doc

# ------------------------------ Main ---------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Search RSS feeds from feeds.txt for keywords and output an Apple-like HTML report.")
    parser.add_argument("--keywords", "-k", type=str, default="", help="Comma-separated keywords (Arabic or English). If omitted, you'll be prompted.")
    parser.add_argument("--field", "-f", choices=("title", "description", "both"), default="both", help="Where to search for keywords.")
    parser.add_argument("--mode", "-m", choices=("any", "all"), default="any", help="Match ANY or ALL of the keywords.")
    parser.add_argument("--output", "-o", type=str, default="", help="Optional explicit output HTML filename. If omitted, auto-name includes first keyword + timestamp.")
    parser.add_argument("--feeds-file", "-F", type=str, default="feeds.txt", help='Path to feeds file (default: "feeds.txt").')
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds.")
    parser.add_argument("--concurrency", "-c", type=int, default=16, help="Max concurrent feed fetches.")
    parser.add_argument("--max", type=int, default=0, help="Optional cap on number of results in HTML after sorting. 0 = unlimited.")
    args = parser.parse_args(argv)

    # Load feeds (feeds.txt is the default and REQUIRED by design)
    if not os.path.exists(args.feeds_file):
        # Create a friendly sample to help the user
        sample = """# feeds.txt — add one RSS/Atom URL per line. Lines starting with '#' are comments.
https://feeds.bbci.co.uk/news/rss.xml
http://rss.cnn.com/rss/edition.rss
# https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
"""
        try:
            with open(args.feeds_file, "w", encoding="utf-8") as f:
                f.write(sample)
            print(f"[i] '{args.feeds_file}' not found. A sample file has been created. Please edit it to your needs.", file=sys.stderr)
        except Exception:
            pass
        print(f"[!] Feeds file not found: {args.feeds_file}", file=sys.stderr)
        print('    Create/edit "feeds.txt" with one RSS/Atom URL per line. Lines starting with "#" are ignored.', file=sys.stderr)
        return 2

    try:
        feeds = load_feeds_from_txt(args.feeds_file)
    except Exception as e:
        print(f"[!] Failed to read feeds file: {e}", file=sys.stderr)
        return 2
    if not feeds:
        print("[!] No feeds found in feeds.txt. Add at least one URL.", file=sys.stderr)
        return 2

    # Keywords
    raw_kw = args.keywords.strip()
    if not raw_kw:
        try:
            raw_kw = input("Enter keywords (comma-separated, Arabic or English): ").strip()
        except EOFError:
            raw_kw = ""
    keywords = parse_keywords(raw_kw)
    if not keywords:
        print("[!] No keywords provided. Exiting.", file=sys.stderr)
        return 2

    # Optional interactive tweak for field & mode (keeps defaults if blank/invalid)
    try:
        field_in = input(f"Search field [both/title/description] (default {args.field}): ").strip().lower()
        if field_in in {"both","title","description"}:
            args.field = field_in
        mode_in = input(f"Match mode [any/all] (default {args.mode}): ").strip().lower()
        if mode_in in {"any","all"}:
            args.mode = mode_in
    except EOFError:
        pass

    # First keyword for filename
    original_first_kw = (raw_kw.replace("\n", ",").split(",")[0].strip() if raw_kw else "") or "results"
    slug_kw = slugify_for_filename(original_first_kw, fallback="results")

    # Fetch concurrently
    fetched: List[Tuple[str, Any, Optional[Exception]]] = []
    failed: List[Tuple[str, Optional[Exception]]] = []
    with futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        tasks = [ex.submit(fetch_and_parse, url, args.timeout) for url in feeds]
        for t in futures.as_completed(tasks):
            url, parsed, err = t.result()
            if err is not None or not safe_entries(parsed):
                failed.append((url, err))
            fetched.append((url, parsed, err))

    # Filter entries
    matched: List[Dict[str, Any]] = []
    seen_links: set = set()
    for url, parsed, _err in fetched:
        for e in safe_entries(parsed):
            text = field_text(e, args.field)
            if not text:
                continue
            if matches(text, keywords, args.mode):
                link = e.get("link") or ""
                if link and not (link.startswith("http://") or link.startswith("https://")):
                    continue
                if link in seen_links:
                    continue
                seen_links.add(link)
                source = ""
                try:
                    host = urlparse(link).netloc
                    source = host
                except Exception:
                    pass
                dt_epoch = entry_datetime(e)
                dt = datetime.fromtimestamp(dt_epoch) if dt_epoch else None
                date_str = dt.strftime('%b %d, %Y') if dt else ""
                matched.append({
                    "title": e.get("title", ""),
                    "link": link,
                    "summary": e.get("summary", "") or e.get("description", ""),
                    "source": source,
                    "date": dt_epoch,
                    "date_str": date_str,
                })

    # Sort newest first
    matched.sort(key=lambda r: r.get("date", 0.0), reverse=True)
    if args.max and args.max > 0:
        matched = matched[: args.max]

    # Output path
    if args.output:
        out_path = args.output
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"results_{slug_kw}_{stamp}.html"

    html_doc = render_html(
        results=matched,
        keywords=keywords,
        search_field=args.field,
        mode=args.mode,
        generated_at=datetime.now(),
        total_feeds=len(feeds),
        failed_feeds=failed,
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"[+] Wrote {len(matched)} matches to: {out_path}")
    if failed:
        print(f"[i] {len(failed)} feed(s) failed or returned empty. See the header note in the HTML for a list.", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())