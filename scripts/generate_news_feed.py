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
# Writing Styles (10 distinct voices for variety)
# ---------------------------------------------------------------------------

STYLE_DEFINITIONS = {
    "direct": {
        "prompt_block": """STYLE "direct" (Direct & Punchy):
- Short, declarative sentences. Under 15 words each.
- Headline: bold statement, max 60 chars. Can end with a period.
- what_changed: max 15 words. Drop unnecessary words.
- why_care: starts with "This means" or "That means" or "Bottom line:".
- what_to_do: starts with an imperative verb. No "Consider" or "Research". Use "Set up", "Switch to", "Test", "Add".
- DO NOT use passive voice. DO NOT use "could" or "might".
EXAMPLE:
  headline: "Google just killed its code review tool."
  what_changed: "Google deprecated Critique and moved teams to Copilot-based code reviews."
  why_care: "This means AI code review is now table stakes, not optional."
  what_to_do: "Set up Copilot code review on your main repo this week."
""",
    },
    "analytical": {
        "prompt_block": """STYLE "analytical" (Analytical & Data-Driven):
- Measured tone. Use data framing and cause-effect structure.
- Headline: includes a number or data point when possible.
- what_changed: includes a specific number, comparison, or trend.
- why_care: uses "which means" or "the implication is" connector.
- what_to_do: two-part action with "then" connecting them.
- DO NOT use exclamation marks. DO NOT use casual language.
EXAMPLE:
  headline: "OpenAI's 300M users signal a shift in enterprise adoption"
  what_changed: "OpenAI reported 300 million weekly active users, up from 200 million in August, with enterprise seats growing 4x."
  why_care: "The implication is that AI tools are no longer experimental, they are becoming standard workflow in your industry."
  what_to_do: "Audit which AI tools your team already uses informally, then propose a formal adoption plan to leadership."
""",
    },
    "conversational": {
        "prompt_block": """STYLE "conversational" (Casual & Friendly):
- Casual tone. Use contractions. Feels like a smart friend explaining over coffee.
- Headline: can start with "So," or "Turns out" or drop the formal opener.
- what_changed: uses "basically" or "essentially" or "in short".
- why_care: addresses "for you" directly and personally.
- what_to_do: uses "Try" or "Check out" or "Give X a look".
- DO NOT use formal or corporate language. Write like you talk.
EXAMPLE:
  headline: "So Microsoft just made Copilot free for everyone"
  what_changed: "Basically, Microsoft removed the paywall on Copilot and it now works across all Office apps for free."
  why_care: "For you, this means every competitor just got a writing and coding assistant at no cost."
  what_to_do: "Try using Copilot for one real task today and see where it actually saves you time."
""",
    },
    "narrative": {
        "prompt_block": """STYLE "narrative" (Story-Driven):
- Opens with context or a "when X happened" frame. Creates a mini story arc.
- Headline: narrative hook that makes you want to know what happened next.
- what_changed: uses "When [actor] [action], [consequence]" structure.
- why_care: connects to the reader's personal professional story.
- what_to_do: frames the action as the reader's next chapter.
- DO NOT use dry, factual framing. Make it feel like a story unfolding.
EXAMPLE:
  headline: "When Anthropic hired 200 safety researchers, the industry noticed"
  what_changed: "When Anthropic announced its largest hiring wave of 200 AI safety researchers, it signaled that responsible AI is becoming a competitive advantage."
  why_care: "If your company builds AI products, customers will start asking about safety the same way they ask about uptime."
  what_to_do: "Start documenting your team's AI safety practices before clients and regulators ask for them."
""",
    },
    "question": {
        "prompt_block": """STYLE "question" (Question-Led & Socratic):
- Opens with a provocative or thought-provoking question.
- Headline: MUST be a question ending with "?".
- what_changed: answers the question directly and factually.
- why_care: asks a second, personal question that makes the reader think.
- what_to_do: provides a direct, actionable answer to that personal question.
- DO NOT use rhetorical questions with obvious answers. Make the reader genuinely think.
EXAMPLE:
  headline: "What happens when AI writes 90% of new code?"
  what_changed: "A new study found that AI-generated code now accounts for over 90% of first-draft commits at top tech companies."
  why_care: "If most code is AI-generated, what does your value as a developer actually become?"
  what_to_do: "Shift 30 minutes of your learning time this week from syntax to system design and architecture."
""",
    },
    "contrarian": {
        "prompt_block": """STYLE "contrarian" (Challenges the Obvious Take):
- Challenges the consensus. "Everyone says X, but actually..." energy.
- Headline: contrarian framing that surprises. Can be two short sentences.
- what_changed: states the consensus view, then the counterpoint or nuance.
- why_care: starts with "But here's what most people miss:" or "The real story is:".
- what_to_do: the non-obvious, smarter action most people won't take.
- DO NOT be contrarian just for shock value. The counterpoint must be genuinely insightful.
EXAMPLE:
  headline: "Everyone's excited about this AI model. They shouldn't be."
  what_changed: "Meta released a new open-source model that benchmarks well, but independent tests show it hallucinates 40% more than GPT-4."
  why_care: "The real story is: most teams will rush to use it because it's free, but your error rates will spike in production."
  what_to_do: "Run the model on your own test cases before trusting any third-party benchmark."
""",
    },
    "mentor": {
        "prompt_block": """STYLE "mentor" (Career Coach & Encouraging):
- Warm but direct. Like a senior colleague giving career advice.
- Headline: signals an opportunity or learning moment. Can start with "This is your signal to..."
- what_changed: factual and clear.
- why_care: uses "This is the kind of shift that..." or "Being early to this gives you...".
- what_to_do: framed as a growth or career move, not just a task.
- DO NOT be preachy or condescending. Be genuinely helpful and encouraging.
EXAMPLE:
  headline: "This is your signal to learn vector databases"
  what_changed: "Pinecone raised $100M and reported 5x enterprise adoption in six months."
  why_care: "This is the kind of growth that creates a skills gap, and being early gives you a real advantage."
  what_to_do: "Complete one vector database tutorial this week, even a basic one puts you ahead."
""",
    },
    "numbers": {
        "prompt_block": """STYLE "numbers" (Numbers-First, Bloomberg Energy):
- Leads with the most striking number. Financial newsletter energy.
- Headline: MUST start with a number or dollar amount. Short and punchy.
- what_changed: unpacks what the number means concretely.
- why_care: puts the number in personal, professional context for the reader.
- what_to_do: a quantified or time-boxed action (include a number or deadline).
- DO NOT bury the number. It must be the first thing the reader sees.
EXAMPLE:
  headline: "$14.6 billion. That's Nscale's new valuation."
  what_changed: "Nscale closed a massive round to build GPU cloud infrastructure, making it Europe's largest AI funding deal."
  why_care: "When this much capital flows into AI infrastructure, compute costs drop for everyone building AI products."
  what_to_do: "Compare your current cloud GPU costs against at least 2 new providers within 48 hours."
""",
    },
    "context": {
        "prompt_block": """STYLE "context" (Big Picture, Zooms Out):
- Explains the bigger picture before diving into the news. Adds historical or industry context.
- Headline: uses "Why X matters more than you think" or "The real significance of X" framing.
- what_changed: the news itself plus one sentence of background context.
- why_care: connects this event to a longer trend or pattern the reader should track.
- what_to_do: strategic and forward-looking, not tactical.
- DO NOT just restate the news. Add genuine context that makes the reader smarter.
EXAMPLE:
  headline: "Why Apple's M4 chip matters more than another iPhone launch"
  what_changed: "Apple's new M4 iPad continues a three-year trend of bringing desktop-class AI processing to mobile devices."
  why_care: "For five years AI required cloud GPUs, but on-device AI is closing that gap, which reshapes what you can build."
  what_to_do: "Evaluate which of your AI features could run on-device instead of in the cloud."
""",
    },
    "urgent": {
        "prompt_block": """STYLE "urgent" (Time-Sensitive & Actionable):
- High energy. Creates genuine urgency without being clickbait. Time-sensitive framing.
- Headline: uses "now", "today", "this week", or "starting [date]".
- what_changed: emphasizes speed, recency, or a deadline.
- why_care: includes a timeframe like "within [X days/weeks]" or "before [event]".
- what_to_do: specific and time-boxed with a clear deadline.
- DO NOT create false urgency. Only use this style when there is genuine time pressure.
EXAMPLE:
  headline: "This regulation change affects your AI products starting next month"
  what_changed: "The EU AI Act's first compliance deadline hits April 2026, requiring risk classification for all AI systems sold in Europe."
  why_care: "If you ship AI products to European customers, you have less than 30 days to classify and document your systems."
  what_to_do: "Download the EU AI Act checklist today and map your products against the four risk tiers."
""",
    },
}

# Maps impact types to 3 preferred writing styles (best fit first)
STYLE_AFFINITY = {
    "threat":        ["urgent", "contrarian", "direct"],
    "opportunity":   ["mentor", "numbers", "conversational"],
    "industryShift": ["context", "analytical", "narrative"],
    "positive":      ["mentor", "conversational", "context"],
    "skillDemand":   ["mentor", "urgent", "question"],
    "toolRelease":   ["direct", "conversational", "numbers"],
    "research":      ["analytical", "question", "context"],
    "funding":       ["numbers", "analytical", "narrative"],
    "roleChange":    ["question", "mentor", "urgent"],
    "milestone":     ["narrative", "numbers", "direct"],
}


def classify_impact_for_style(article: dict) -> str:
    """Classify article impact type for style selection (mirrors iOS logic)."""
    text = (article["headline"] + " " + article["description"]).lower()
    if any(kw in text for kw in ["launch", "release", "new tool", "new ai", "agent"]):
        return "toolRelease"
    if any(kw in text for kw in ["replace", "layoff", "cut jobs", "eliminate", "automate"]):
        return "threat"
    if any(kw in text for kw in ["funding", "acquisition", "acquires", "raises", "valuation", "billion", "investment"]):
        return "funding"
    if any(kw in text for kw in ["study", "research", "paper", "benchmark", "findings"]):
        return "research"
    if any(kw in text for kw in ["breakthrough", "record", "first ever", "milestone", "surpass"]):
        return "milestone"
    if any(kw in text for kw in ["new role", "job title", "role evolv", "responsibilities"]):
        return "roleChange"
    if any(kw in text for kw in ["opportunity", "salary", "demand", "hiring", "new jobs"]):
        return "opportunity"
    if any(kw in text for kw in ["skill", "upskill", "training", "certification", "learn"]):
        return "skillDemand"
    if any(kw in text for kw in ["protect", "safe", "regulation", "oversight"]):
        return "positive"
    return "industryShift"


def assign_styles(articles: list[dict]) -> list[str]:
    """Assign a writing style to each article. Hash-based, deterministic, no consecutive repeats."""
    styles = []
    for i, art in enumerate(articles):
        impact = classify_impact_for_style(art)
        pool = STYLE_AFFINITY.get(impact, ["direct", "analytical", "conversational"])

        # Hash-based deterministic pick from affinity pool
        headline_hash = int(hashlib.md5(art["headline"].encode()).hexdigest(), 16)
        pick_index = headline_hash % len(pool)
        chosen = pool[pick_index]

        # Avoid consecutive repeats
        if i > 0 and chosen == styles[-1]:
            chosen = pool[(pick_index + 1) % len(pool)]

        styles.append(chosen)
    return styles


# ---------------------------------------------------------------------------
# AI Rewriting
# ---------------------------------------------------------------------------

def clean_for_prompt(text: str) -> str:
    """Remove characters that might confuse JSON parsing in AI responses."""
    text = text.replace('"', "'").replace("\\", "")
    text = re.sub(r"[\x00-\x1f]", " ", text)  # Control characters
    return text.strip()


def build_prompt(articles: list[dict], cluster: dict, style_assignments: list[str]) -> str:
    """Build the rewrite prompt for a single cluster with per-article style assignments."""
    # Collect only the styles we need for this batch
    styles_in_use = set(style_assignments)
    style_block = "\n".join(
        STYLE_DEFINITIONS[s]["prompt_block"] for s in styles_in_use
    )

    articles_text = ""
    for i, art in enumerate(articles):
        headline = clean_for_prompt(art["headline"])
        snippet = clean_for_prompt(art["description"])
        style_name = style_assignments[i]
        articles_text += f"""
Article {i} (USE "{style_name}" STYLE):
Headline: {headline}
Snippet: {snippet}
Source: {art['source']}
"""

    return f"""You rewrite AI news for professionals. Each article MUST be written in a specific style.
Your writing should feel like a premium newsletter (Morning Brew, The Skimm, Bloomberg), not a corporate report.

Target audience: {cluster['name']} - {cluster['description']}

GLOBAL RULES:
- NEVER use em dashes (--). Use commas, periods, or rewrite the sentence.
- Preserve company names, tool names, dollar amounts, and dates exactly.
- Use plain language. No jargon. Address the reader as "you/your".
- CRITICAL: Each article has a DIFFERENT assigned style. Follow that style's rules EXACTLY.

SMART ACTION RULES for "what_to_do":
- If this article has a GENUINE, SPECIFIC action for {cluster['name']}, write a concrete action step.
- If this article is NOT directly relevant to {cluster['name']}'s daily work, write a perspective or takeaway instead.
  Use framing like: "Worth knowing:", "The bigger picture:", or "Keep an eye on this:" followed by an insightful observation.
- NEVER write generic filler like "Research how...", "Stay informed about...", "Consider the implications of...", or "Monitor developments in...".

STYLE DEFINITIONS:
{style_block}

{articles_text}

Respond with ONLY a JSON array, no markdown:
[{{"id": 0, "headline": "...", "what_changed": "...", "why_care": "...", "what_to_do": "...", "style": "..."}}, ...]"""


def rewrite_gemini(articles: list[dict], cluster: dict, style_assignments: list[str]) -> list[dict]:
    """Call Gemini Flash to rewrite articles for a cluster."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    prompt = build_prompt(articles, cluster, style_assignments)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        # Log the response body for debugging
        if hasattr(e, 'read'):
            body = e.read().decode('utf-8', errors='replace')
            print(f"    Gemini error body: {body[:500]}")
        raise

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


def rewrite_haiku(articles: list[dict], cluster: dict, style_assignments: list[str]) -> list[dict]:
    """Call Claude Haiku to rewrite articles for a cluster."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    prompt = build_prompt(articles, cluster, style_assignments)
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "temperature": 0.5,
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


def validate_style(rewrite: dict, expected_style: str) -> bool:
    """Basic heuristic check that the rewrite matches its assigned style."""
    headline = rewrite.get("headline", "")
    if expected_style == "numbers" and not re.match(r'^[$\d]', headline):
        return False
    if expected_style == "question" and not headline.rstrip().endswith("?"):
        return False
    return True


def generate_rewrites(articles: list[dict], provider: str = "gemini") -> dict:
    """Generate rewrites for all 18 clusters with varied writing styles."""
    rewrite_fn = rewrite_gemini if provider == "gemini" else rewrite_haiku
    all_rewrites = {}

    # Assign styles once (same styles for all clusters, based on article content)
    style_assignments = assign_styles(articles)
    for i, (art, style) in enumerate(zip(articles, style_assignments)):
        impact = classify_impact_for_style(art)
        print(f"  Article {i}: impact={impact}, style={style}")

    for cluster in CLUSTERS:
        cluster_id = cluster["id"]
        print(f"  Rewriting for {cluster['name']}...")
        try:
            rewrites = rewrite_fn(articles, cluster, style_assignments)
            # Log style validation
            for rw in rewrites:
                idx = rw.get("id", 0)
                if idx < len(style_assignments):
                    expected = style_assignments[idx]
                    if not validate_style(rw, expected):
                        print(f"    [WARN] Article {idx} style mismatch: expected={expected}, headline='{rw.get('headline', '')[:40]}'")
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
                    "style": style_assignments[i] if i < len(style_assignments) else "direct",
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
    merged_articles = merged_articles[:168]  # 7 days x 24 articles/day

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
    parser.add_argument("--count", type=int, default=1,
                        help="Number of articles to pick (default: 1)")
    args = parser.parse_args()

    # Load existing feed.json FIRST so we can skip already-covered articles
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "feed.json"
    existing_feed = None
    existing_headline_hashes = set()
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing_feed = json.load(f)
            existing_count = len(existing_feed.get("articles", []))
            print(f"Loaded existing feed: {existing_count} articles")
            # Build set of headline hashes already in the feed
            for art in existing_feed.get("articles", []):
                h = hashlib.md5(art.get("headline", "").encode()).hexdigest()[:12]
                existing_headline_hashes.add(h)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Could not load existing feed: {e}")

    # Fetch all feeds
    all_articles = fetch_all_feeds()
    if not all_articles:
        print("ERROR: No articles fetched from any feed!")
        sys.exit(1)

    # Filter out articles already in the feed (by headline hash)
    fresh_articles = []
    for art in all_articles:
        h = hashlib.md5(art["headline"].encode()).hexdigest()[:12]
        if h not in existing_headline_hashes:
            fresh_articles.append(art)
    print(f"Fresh articles (not in feed yet): {len(fresh_articles)} / {len(all_articles)}")

    # Pick top articles from fresh ones; fall back to all if no fresh articles
    candidates = fresh_articles if fresh_articles else all_articles
    top = pick_top_articles(candidates, count=args.count)
    print(f"\nTop {len(top)} articles selected:")
    for i, art in enumerate(top):
        print(f"  {i+1}. [{art['source']}] {art['headline'][:80]}")

    # If the picked article is already in the feed (no fresh articles available), skip rewriting
    picked_hash = hashlib.md5(top[0]["headline"].encode()).hexdigest()[:12] if top else ""
    if picked_hash in existing_headline_hashes:
        print("\nNo new articles found. Feed is up to date.")
        sys.exit(0)

    # Generate run ID
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if args.dry_run:
        print("\n[DRY RUN] Skipping AI rewrites")
        rewrites = {}
    else:
        print(f"\nGenerating rewrites with {args.provider}...")
        rewrites = generate_rewrites(top, provider=args.provider)
        print(f"Done! {len(rewrites)} clusters rewritten")

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
