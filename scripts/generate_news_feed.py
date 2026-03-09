#!/usr/bin/env python3
"""
AI Job Threat Monitor - Personalized News Feed Generator

Fetches top AI news from publisher RSS feeds, picks the top 3 most impactful
articles, then generates personalized rewrites for 18 industry clusters using
Gemini Flash (default) or Claude Haiku.

Output: news-feed/output/feed.json — fetched by the iOS app.

Usage:
    python3 scripts/generate_news_feed.py                    # Gemini Flash (default)
    python3 scripts/generate_news_feed.py --provider haiku   # Claude Haiku
    python3 scripts/generate_news_feed.py --dry-run          # Skip AI, output raw articles

Environment variables:
    GEMINI_API_KEY    - Google AI Studio key (for Gemini Flash)
    ANTHROPIC_API_KEY - Anthropic key (for Claude Haiku)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEEDS = [
    ("https://openai.com/news/rss.xml", "OpenAI", "AI Tools"),
    ("https://blog.google/technology/ai/rss/", "Google AI", "AI Research"),
    ("https://engineering.fb.com/feed/", "Meta Engineering", "AI Research"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch", "AI Industry"),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge", "AI Industry"),
    ("https://www.technologyreview.com/topic/artificial-intelligence/feed/", "MIT Tech Review", "AI Research"),
    ("https://arstechnica.com/ai/feed/", "Ars Technica", "AI Industry"),
    ("https://venturebeat.com/category/ai/feed/", "VentureBeat", "AI Industry"),
    ("https://www.marktechpost.com/feed/", "MarkTechPost", "AI Research"),
    ("https://the-decoder.com/feed/", "The Decoder", "AI Tools"),
    ("https://www.wired.com/feed/tag/ai/latest/rss", "Wired", "AI Industry"),
    ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "CNBC", "AI Industry"),
    ("https://www.theguardian.com/technology/artificialintelligenceai/rss", "The Guardian", "AI Industry"),
]

CLUSTERS = [
    {
        "id": "software_engineering",
        "name": "Software Engineers",
        "description": "software developers, DevOps engineers, cloud architects, QA engineers, full-stack developers",
        "industries": ["it_technology"],
    },
    {
        "id": "data_ai",
        "name": "Data & AI Professionals",
        "description": "data scientists, ML engineers, data analysts, AI researchers, data engineers",
        "industries": ["it_technology", "science"],
    },
    {
        "id": "cybersecurity",
        "name": "Cybersecurity Professionals",
        "description": "penetration testers, SOC analysts, CISOs, security engineers, threat analysts",
        "industries": ["it_technology", "government"],
    },
    {
        "id": "design_ux",
        "name": "Designers & UX Professionals",
        "description": "graphic designers, UX designers, UI designers, motion designers, product designers",
        "industries": ["creative"],
    },
    {
        "id": "product_project",
        "name": "Product & Project Managers",
        "description": "product managers, project managers, scrum masters, business analysts, program managers",
        "industries": ["operations", "it_technology"],
    },
    {
        "id": "marketing",
        "name": "Marketing Professionals",
        "description": "digital marketers, content marketers, SEO specialists, social media managers, brand managers",
        "industries": ["marketing"],
    },
    {
        "id": "sales",
        "name": "Sales Professionals",
        "description": "account executives, SDRs, account managers, sales engineers, business development reps",
        "industries": ["sales"],
    },
    {
        "id": "customer_support",
        "name": "Customer Support Professionals",
        "description": "customer service reps, customer success managers, call center agents, support specialists",
        "industries": ["customer_support"],
    },
    {
        "id": "finance",
        "name": "Finance Professionals",
        "description": "accountants, financial analysts, investment analysts, auditors, banking professionals",
        "industries": ["finance"],
    },
    {
        "id": "legal",
        "name": "Legal Professionals",
        "description": "attorneys, paralegals, compliance officers, legal operations managers, contract specialists",
        "industries": ["legal"],
    },
    {
        "id": "hr",
        "name": "HR Professionals",
        "description": "recruiters, HR business partners, L&D managers, people ops, compensation analysts",
        "industries": ["hr"],
    },
    {
        "id": "healthcare",
        "name": "Healthcare Professionals",
        "description": "nurses, doctors, medical coders, clinical data analysts, health information managers",
        "industries": ["healthcare"],
    },
    {
        "id": "education",
        "name": "Education Professionals",
        "description": "teachers, professors, instructional designers, corporate trainers, education technology specialists",
        "industries": ["education"],
    },
    {
        "id": "media_content",
        "name": "Media & Content Professionals",
        "description": "journalists, editors, podcast producers, writers, fact-checkers, screenwriters",
        "industries": ["media"],
    },
    {
        "id": "creative_entertainment",
        "name": "Creative & Entertainment Professionals",
        "description": "video editors, motion graphics designers, animators, video producers, esports managers",
        "industries": ["creative", "entertainment"],
    },
    {
        "id": "operations_supply",
        "name": "Operations & Supply Chain Professionals",
        "description": "operations managers, supply chain analysts, logistics coordinators, warehouse managers, manufacturing specialists",
        "industries": ["operations", "manufacturing", "transportation"],
    },
    {
        "id": "real_estate_construction",
        "name": "Real Estate & Construction Professionals",
        "description": "real estate agents, architects, surveyors, property managers, construction estimators",
        "industries": ["real_estate", "construction"],
    },
    {
        "id": "science_research",
        "name": "Science & Research Professionals",
        "description": "researchers, applied scientists, lab technicians, AI safety researchers, environmental scientists",
        "industries": ["science", "energy", "agriculture"],
    },
]

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "about", "between",
    "but", "and", "or", "nor", "not", "so", "yet", "both", "either",
    "its", "it", "this", "that", "these", "those", "my", "your", "his",
    "her", "our", "their", "what", "which", "who", "whom", "how", "when",
    "where", "why", "all", "each", "every", "any", "few", "more", "most",
    "new", "says", "said", "report", "reports", "according", "just", "now",
    "also", "than", "then", "very", "here", "there", "up", "out", "over",
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "news-feed" / "output"

# ---------------------------------------------------------------------------
# RSS Fetching
# ---------------------------------------------------------------------------

def fetch_feed(url: str, source: str, topic: str) -> list[dict]:
    """Fetch and parse a single RSS/Atom feed."""
    try:
        req = Request(url, headers={"User-Agent": "AIJobMonitor/1.0 (RSS Reader)"})
        with urlopen(req, timeout=10) as resp:
            data = resp.read()
    except (URLError, TimeoutError, OSError) as e:
        print(f"  [SKIP] {source}: {e}")
        return []

    articles = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        print(f"  [SKIP] {source}: invalid XML")
        return []

    # Handle namespaces
    ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/"}

    # Try RSS 2.0 first
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        desc = strip_html((item.findtext("description") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        articles.append({
            "headline": title,
            "description": truncate(desc or title, 500),
            "link": link,
            "source": source,
            "topic": topic,
            "published_at": parse_date(pub_date),
        })

    # Try Atom if no RSS items found
    if not articles:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            summary = strip_html((
                entry.findtext("{http://www.w3.org/2005/Atom}summary")
                or entry.findtext("{http://www.w3.org/2005/Atom}content")
                or ""
            ).strip())
            link_el = entry.find("{http://www.w3.org/2005/Atom}link[@rel='alternate']")
            if link_el is None:
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.get("href", "") if link_el is not None else ""
            pub = (
                entry.findtext("{http://www.w3.org/2005/Atom}published")
                or entry.findtext("{http://www.w3.org/2005/Atom}updated")
                or ""
            ).strip()
            if not title:
                continue
            articles.append({
                "headline": title,
                "description": truncate(summary or title, 500),
                "link": link,
                "source": source,
                "topic": topic,
                "published_at": parse_date(pub),
            })

    # Also try plain Atom (no namespace)
    if not articles:
        for entry in root.iter("entry"):
            title = (entry.findtext("title") or "").strip()
            summary = strip_html((entry.findtext("summary") or entry.findtext("content") or "").strip())
            link_el = entry.find("link[@rel='alternate']")
            if link_el is None:
                link_el = entry.find("link")
            link = link_el.get("href", "") if link_el is not None else ""
            pub = (entry.findtext("published") or entry.findtext("updated") or "").strip()
            if not title:
                continue
            articles.append({
                "headline": title,
                "description": truncate(summary or title, 500),
                "link": link,
                "source": source,
                "topic": topic,
                "published_at": parse_date(pub),
            })

    # Cap per feed to avoid processing massive backlogs (e.g. OpenAI serves 800+)
    articles = articles[:20]
    print(f"  [{source}] {len(articles)} articles")
    return articles


def fetch_all_feeds() -> list[dict]:
    """Fetch all feeds in sequence, deduplicate, sort by date."""
    print("Fetching RSS feeds...")
    all_articles = []
    for url, source, topic in FEEDS:
        all_articles.extend(fetch_feed(url, source, topic))

    # Deduplicate
    unique = deduplicate(all_articles)
    # Sort newest first
    unique.sort(key=lambda a: a["published_at"], reverse=True)
    print(f"Total: {len(all_articles)} raw -> {len(unique)} unique articles")
    return unique


# ---------------------------------------------------------------------------
# Deduplication (mirrors iOS fingerprinting logic)
# ---------------------------------------------------------------------------

def fingerprint(headline: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", headline.lower())
    # Normalize common number abbreviations (110b -> 110 billion, 5m -> 5 million)
    cleaned = re.sub(r"(\d+)b\b", r"\1 billion", cleaned)
    cleaned = re.sub(r"(\d+)m\b", r"\1 million", cleaned)
    cleaned = re.sub(r"(\d+)k\b", r"\1 thousand", cleaned)
    return {w for w in cleaned.split() if len(w) > 2 and w not in STOP_WORDS}


def are_same_story(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    shared = a & b
    smaller = min(len(a), len(b))
    ratio = len(shared) / smaller
    # Standard threshold
    if ratio >= 0.5:
        return True
    # Lower threshold if shared words include a proper noun + number (strong entity match)
    # e.g., "openai" + "110" + "billion" = clearly same story even if other words differ
    has_number = any(w.isdigit() or w.endswith(("billion", "million", "thousand")) for w in shared)
    has_entity = len(shared) >= 2
    if has_number and has_entity and ratio >= 0.3:
        return True
    return False


def deduplicate(articles: list[dict]) -> list[dict]:
    unique = []
    fps = []
    # Sort oldest first so original reporter wins
    sorted_arts = sorted(articles, key=lambda a: a["published_at"])
    for art in sorted_arts:
        fp = fingerprint(art["headline"])
        if not any(are_same_story(fp, existing) for existing in fps):
            unique.append(art)
            fps.append(fp)
    return unique


# ---------------------------------------------------------------------------
# Article Selection (pick top 3 most impactful)
# ---------------------------------------------------------------------------

IMPACT_KEYWORDS = {
    "high": ["replace", "layoff", "eliminate", "automate", "cut jobs", "fired",
             "launch", "released", "breakthrough", "regulation", "ban", "billion"],
    "medium": ["tool", "model", "update", "partnership", "invest", "hire",
               "skill", "demand", "salary", "opportunity"],
}


def score_article(article: dict) -> float:
    """Score articles by impact (higher = more newsworthy for our audience)."""
    text = (article["headline"] + " " + article["description"]).lower()
    score = 0.0
    for kw in IMPACT_KEYWORDS["high"]:
        if kw in text:
            score += 3.0
    for kw in IMPACT_KEYWORDS["medium"]:
        if kw in text:
            score += 1.0
    # Heavily penalize old articles, boost fresh ones
    try:
        age_hours = (datetime.now(timezone.utc) - datetime.fromisoformat(article["published_at"])).total_seconds() / 3600
        if age_hours < 6:
            score += 5.0
        elif age_hours < 12:
            score += 3.0
        elif age_hours < 24:
            score += 1.0
        elif age_hours > 72:
            score -= 10.0  # 3+ days old = almost never pick
        elif age_hours > 48:
            score -= 5.0
    except (ValueError, TypeError):
        pass
    # Boost diverse sources (prefer not all from same source)
    return score


def pick_top_articles(articles: list[dict], count: int = 3) -> list[dict]:
    """Pick top N articles, ensuring source diversity."""
    scored = sorted(articles, key=score_article, reverse=True)
    picked = []
    sources_used = set()
    for art in scored:
        if len(picked) >= count:
            break
        # Allow max 1 per source in the top picks
        if art["source"] in sources_used and len(picked) < count - 1:
            continue
        picked.append(art)
        sources_used.add(art["source"])
    # Fill remaining slots if source diversity left gaps
    if len(picked) < count:
        for art in scored:
            if len(picked) >= count:
                break
            if art not in picked:
                picked.append(art)
    return picked[:count]


# ---------------------------------------------------------------------------
# AI Rewriting
# ---------------------------------------------------------------------------

def clean_for_prompt(text: str) -> str:
    """Remove characters that might confuse JSON parsing in AI responses."""
    text = text.replace('"', "'").replace("\\", "")
    text = re.sub(r"[\x00-\x1f]", " ", text)  # Control characters
    return text.strip()


def build_prompt(articles: list[dict], cluster: dict) -> str:
    """Build the rewrite prompt for a single cluster."""
    articles_text = ""
    for i, art in enumerate(articles):
        headline = clean_for_prompt(art["headline"])
        snippet = clean_for_prompt(art["description"])
        articles_text += f"""
Article {i}:
Headline: {headline}
Snippet: {snippet}
Source: {art['source']}
"""

    return f"""You rewrite AI news for professionals in a specific industry.

Target audience: {cluster['name']} - {cluster['description']}

RULES:
- NEVER use em dashes (--). Use commas, periods, or rewrite.
- Preserve company names, tool names, dollar amounts, dates exactly.
- Write in plain language. No jargon. Use "you/your" to address the reader.
- Each field must be exactly ONE sentence. Keep it punchy and specific.
- The "what_to_do" must be a concrete, actionable step (not "stay informed").

For each article below, provide:
1. headline: Rewritten for this audience (max 80 chars, preserve key facts)
2. what_changed: One sentence - what concretely happened
3. why_care: One sentence - why this matters specifically for {cluster['name']}
4. what_to_do: One sentence - specific action they should take this week

{articles_text}

Respond with ONLY a JSON array, no markdown:
[{{"id": 0, "headline": "...", "what_changed": "...", "why_care": "...", "what_to_do": "..."}}, ...]"""


def rewrite_gemini(articles: list[dict], cluster: dict) -> list[dict]:
    """Call Gemini Flash to rewrite articles for a cluster."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    prompt = build_prompt(articles, cluster)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    # Gemini 2.5 thinking models may have multiple parts (thought + text)
    parts = result["candidates"][0]["content"]["parts"]
    text = ""
    for part in parts:
        if "text" in part:
            text = part["text"]  # Use last text part (thoughts come first)
    # Strip markdown fences if present
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def rewrite_haiku(articles: list[dict], cluster: dict) -> list[dict]:
    """Call Claude Haiku to rewrite articles for a cluster."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    prompt = build_prompt(articles, cluster)
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    text = result["content"][0]["text"]
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def generate_rewrites(articles: list[dict], provider: str = "gemini") -> dict:
    """Generate rewrites for all 18 clusters."""
    rewrite_fn = rewrite_gemini if provider == "gemini" else rewrite_haiku
    all_rewrites = {}

    for cluster in CLUSTERS:
        cluster_id = cluster["id"]
        print(f"  Rewriting for {cluster['name']}...")
        try:
            rewrites = rewrite_fn(articles, cluster)
            all_rewrites[cluster_id] = rewrites
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"    [ERROR] {cluster['name']}: {e}")
            # Fallback: use original headlines with generic fields
            all_rewrites[cluster_id] = [
                {
                    "id": i,
                    "headline": art["headline"],
                    "what_changed": art["description"],
                    "why_care": "This AI development could affect how work gets done in your field.",
                    "what_to_do": "Read the full article to assess if this impacts your role.",
                }
                for i, art in enumerate(articles)
            ]

    return all_rewrites


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def build_output(articles: list[dict], rewrites: dict, run_id: str, existing_feed: dict | None = None) -> dict:
    """Build the final JSON output, merging with existing feed if provided.

    Keeps a rolling history of articles (max 50) so the app accumulates news over time.
    New articles go first, then existing articles deduped by headline hash ID.
    Rewrite indices are remapped to match final article positions.
    """
    # Create article entries with stable IDs for new articles
    # Use current generation time as published_at (when we show it to users)
    now_iso = datetime.now(timezone.utc).isoformat()
    new_entries = []
    new_id_by_original_index = {}  # maps original pick index -> hash ID
    for i, art in enumerate(articles):
        art_id = hashlib.md5(art["headline"].encode()).hexdigest()[:12]
        new_entries.append({
            "id": art_id,
            "index": i,  # temporary, will be reassigned
            "headline": art["headline"],
            "description": art["description"],
            "link": art["link"],
            "source": art["source"],
            "topic": art["topic"],
            "published_at": now_iso,
        })
        new_id_by_original_index[i] = art_id

    # Start with new articles
    merged_articles = list(new_entries)
    seen_ids = {a["id"] for a in merged_articles}

    # Merge old articles (dedup by ID)
    old_index_to_id = {}  # maps old feed index -> hash ID (for rewrite remapping)
    if existing_feed:
        for old_art in existing_feed.get("articles", []):
            old_index_to_id[old_art.get("index", -1)] = old_art["id"]
            if old_art["id"] not in seen_ids:
                merged_articles.append(dict(old_art))
                seen_ids.add(old_art["id"])

    # Sort newest first, cap at 50, re-index
    merged_articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    merged_articles = merged_articles[:50]

    # Build final index map: hash ID -> final index
    id_to_final_index = {}
    for i, art in enumerate(merged_articles):
        art["index"] = i
        id_to_final_index[art["id"]] = i

    # Merge rewrites with index remapping
    merged_rewrites: dict[str, list] = {}
    for cluster_id in {*rewrites.keys(), *(existing_feed or {}).get("rewrites", {}).keys()}:
        cluster_items = []
        seen_headlines = set()

        # New rewrites first (remap from original pick index -> final index)
        for rw in rewrites.get(cluster_id, []):
            orig_idx = rw.get("id", -1)
            art_hash = new_id_by_original_index.get(orig_idx)
            final_idx = id_to_final_index.get(art_hash, -1) if art_hash else -1
            if final_idx < 0:
                continue  # article was trimmed
            rw_copy = dict(rw)
            rw_copy["id"] = final_idx
            # Add source from article
            if art_hash and not rw_copy.get("source"):
                for a in merged_articles:
                    if a["id"] == art_hash:
                        rw_copy["source"] = a.get("source", "")
                        break
            cluster_items.append(rw_copy)
            seen_headlines.add(rw_copy.get("headline", "").lower())

        # Old rewrites (remap from old index -> final index)
        if existing_feed:
            for rw in existing_feed.get("rewrites", {}).get(cluster_id, []):
                hl = rw.get("headline", "").lower()
                if hl in seen_headlines:
                    continue
                old_idx = rw.get("id", -1)
                art_hash = old_index_to_id.get(old_idx)
                final_idx = id_to_final_index.get(art_hash, -1) if art_hash else -1
                if final_idx < 0:
                    continue  # article was trimmed
                rw_copy = dict(rw)
                rw_copy["id"] = final_idx
                cluster_items.append(rw_copy)
                seen_headlines.add(hl)

        # Sort by article index (newest articles first)
        cluster_items.sort(key=lambda r: r.get("id", 999))
        merged_rewrites[cluster_id] = cluster_items

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "articles": merged_articles,
        "rewrites": merged_rewrites,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Handle numeric HTML entities (&#8230; = ellipsis, &#8217; = right quote, etc.)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, word_limit: int) -> str:
    words = text.split()
    if len(words) <= word_limit:
        return text
    return " ".join(words[:word_limit]) + "..."


def parse_date(date_str: str) -> str:
    """Try multiple date formats, return ISO 8601 string."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()

    from email.utils import parsedate_to_datetime
    # Try RFC 2822 (RSS standard)
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except (ValueError, TypeError):
        pass
    # Try ISO 8601
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, TypeError):
        pass
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate personalized AI news feed")
    parser.add_argument("--provider", choices=["gemini", "haiku"], default="gemini",
                        help="AI provider for rewrites (default: gemini)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip AI rewriting, output raw articles only")
    parser.add_argument("--count", type=int, default=5,
                        help="Number of articles to pick (default: 5)")
    args = parser.parse_args()

    # Fetch all feeds
    all_articles = fetch_all_feeds()
    if not all_articles:
        print("ERROR: No articles fetched from any feed!")
        sys.exit(1)

    # Pick top articles
    top = pick_top_articles(all_articles, count=args.count)
    print(f"\nTop {len(top)} articles selected:")
    for i, art in enumerate(top):
        print(f"  {i+1}. [{art['source']}] {art['headline'][:80]}")

    # Generate run ID
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if args.dry_run:
        print("\n[DRY RUN] Skipping AI rewrites")
        rewrites = {}
    else:
        print(f"\nGenerating rewrites with {args.provider}...")
        rewrites = generate_rewrites(top, provider=args.provider)
        print(f"Done! {len(rewrites)} clusters rewritten")

    # Load existing feed.json to merge with (rolling history)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "feed.json"
    existing_feed = None
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing_feed = json.load(f)
            existing_count = len(existing_feed.get("articles", []))
            print(f"\nLoaded existing feed: {existing_count} articles")
        except (json.JSONDecodeError, OSError) as e:
            print(f"\nCould not load existing feed: {e}")

    # Build and save output (merges new + existing, keeps up to 50 articles)
    output = build_output(top, rewrites, run_id, existing_feed=existing_feed)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    total = len(output["articles"])
    print(f"\nOutput written to {output_path} ({total} total articles)")

    # Also save a timestamped archive copy
    archive_path = OUTPUT_DIR / f"feed_{run_id}.json"
    with open(archive_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Archive copy: {archive_path}")


if __name__ == "__main__":
    main()
