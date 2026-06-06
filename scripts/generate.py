#!/usr/bin/env python3
"""
The Daily Briefing — newsletter generator.
Fetches RSS feeds, curates with Claude, generates a static HTML edition.
"""

import feedparser
import anthropic
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Section definitions ───────────────────────────────────────────────────────

SECTIONS = {
    "world_news": {
        "title": "World News",
        "subtitle": "Europe, Asia, Africa &amp; Latin America",
        "feeds": [
            "http://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.reuters.com/Reuters/worldNews",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "https://www.theguardian.com/world/rss",
            "https://feeds.npr.org/1004/rss.xml",
        ],
        "keywords": [
            "europe", "european", "eu ", "nato", "russia", "ukraine", "china",
            "beijing", "moscow", "india", "japan", "korea", "asia", "africa",
            "latin america", "brazil", "mexico", "uk", "britain", "france",
            "germany", "italy", "spain", "poland", "putin", "xi jinping",
            "modi", "macron", "g7", "g20", "un ", "united nations", "global",
            "international", "pacific", "atlantic", "arctic", "sanctions",
            "treaty", "summit", "diplomacy", "foreign", "trade war",
        ],
    },
    "middle_east": {
        "title": "The Middle East",
        "subtitle": "Regional politics, conflict, diplomacy &amp; economics",
        "feeds": [
            "https://www.aljazeera.com/xml/rss/all.xml",
            "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
            "https://www.timesofisrael.com/feed/",
            "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
            "https://feeds.reuters.com/Reuters/worldNews",
        ],
        "keywords": [
            "israel", "palestine", "iran", "iraq", "syria", "lebanon",
            "saudi", "yemen", "jordan", "egypt", "middle east", "hamas",
            "hezbollah", "gaza", "west bank", "persian gulf", "arab",
            "netanyahu", "tel aviv", "tehran", "beirut", "cairo", "riyadh",
            "dubai", "qatar", "kuwait", "bahrain", "oman", "turkey",
        ],
    },
    "defense_security": {
        "title": "Defense &amp; National Security",
        "subtitle": "Military, intelligence &amp; security policy",
        "feeds": [
            "https://www.defenseone.com/rss/all/",
            "https://breakingdefense.com/feed/",
            "https://warontherocks.com/feed/",
            "https://www.politico.com/rss/nationalsecurity.xml",
            "https://feeds.reuters.com/Reuters/worldNews",
        ],
        "keywords": [
            "military", "pentagon", "defense", "defence", "nato", "troops",
            "weapon", "missile", "nuclear", "intelligence", "cia", "nsa",
            "fbi", "homeland security", "cyber", "warfare", "combat",
            "air force", "navy", "army", "marines", "special forces",
            "drone", "fighter jet", "submarine", "carrier", "national security",
            "classified", "espionage", "spy", "surveillance", "threat",
            "adversary", "deterrence", "strategic", "geopolitical",
        ],
    },
    "law_courts": {
        "title": "Law &amp; Courts",
        "subtitle": "Significant rulings, litigation &amp; legal developments",
        "feeds": [
            "https://www.scotusblog.com/feed/",
            "https://abovethelaw.com/feed/",
            "https://feeds.reuters.com/reuters/legal",
            "https://www.thenationallawreview.com/rss.xml",
        ],
        "keywords": [
            "court", "ruling", "lawsuit", "judge", "supreme court", "scotus",
            "legal", "verdict", "plaintiff", "defendant", "appeals", "circuit",
            "regulation", "enforcement", "indictment", "charges", "litigation",
            "attorney general", "justice department", "doj", "federal court",
            "trial", "conviction", "acquittal", "settlement", "injunction",
            "statute", "amendment", "legislation", "regulatory",
        ],
    },
    "aviation": {
        "title": "Aviation",
        "subtitle": "Airlines, aircraft, safety &amp; industry news",
        "feeds": [
            "https://simpleflying.com/feed/",
            "http://avherald.com/avh.rss",
            "https://theaircurrent.com/feed/",
            "https://feeds.reuters.com/Reuters/businessNews",
        ],
        "keywords": [
            "airline", "aircraft", "aviation", "flight", "faa", "pilot",
            "airport", "boeing", "airbus", "crash", "incident", "safety",
            "turbulence", "ntsb", "easa", "passengers", "routes", "fleet",
            "takeoff", "landing", "runway", "air traffic", "evtol",
            "supersonic", "737", "787", "a320", "a350", "cargo",
        ],
    },
    "us_politics": {
        "title": "U.S. Politics",
        "subtitle": "Federal politics, legislation &amp; policy debates",
        "feeds": [
            "https://feeds.npr.org/1014/rss.xml",
            "https://www.politico.com/rss/politicopicks.xml",
            "https://thehill.com/feed/",
            "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
            "https://feeds.washingtonpost.com/rss/politics",
        ],
        "keywords": [
            "congress", "senate", "house", "president", "white house",
            "democrat", "republican", "legislation", "bill", "election",
            "trump", "vote", "poll", "cabinet", "executive order",
            "federal", "washington", "administration", "committee",
            "appropriations", "filibuster", "reconciliation", "speaker",
        ],
    },
}

LOOKBACK_HOURS = 27
MAX_ARTICLES_PER_SECTION = 20
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Curation prompt ───────────────────────────────────────────────────────────

CURATION_PROMPT = """You are the editor of a curated daily news briefing with an editorial, neutral tone — like The Browser or Arts & Letters Daily. You are curating the section titled "{section_title}" ({section_subtitle}).

You have been given a list of recent news articles. Your task:

1. SELECT the 3 to 5 most significant, newsworthy stories. Prioritize stories with broad implications over minor developments.
2. DEDUPLICATE — if multiple articles cover the same event, pick the best single source. Do not include near-identical stories.
3. RANK the selected stories from most to least important.
4. WRITE a 2–3 sentence editorial summary for each story. Be factual, concise, and neutral. Do not begin with the headline. Do not editorialize with words like "alarming" or "shocking."
5. WRITE a single sentence explaining why each story matters — the broader significance or what to watch for next.
6. WRITE a short, descriptive headline (your own words, not copied verbatim from the source).

Return ONLY valid JSON. No markdown fences, no explanation text outside the JSON:
{{
  "stories": [
    {{
      "headline": "Your short, descriptive headline",
      "source": "Publication name",
      "url": "Article URL",
      "summary": "Your 2-3 sentence editorial summary.",
      "why_it_matters": "One sentence on broader significance."
    }}
  ]
}}

Articles to evaluate:
{articles_json}"""


# ── Feed fetching ─────────────────────────────────────────────────────────────

def fetch_articles(feeds, keywords):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    articles = []
    seen_titles = set()

    for url in feeds:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "DailyBriefingBot/1.0"})
            for entry in feed.entries:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", "").strip()

                raw_summary = (
                    getattr(entry, "summary", "")
                    or getattr(entry, "description", "")
                    or ""
                )
                summary = re.sub(r"<[^>]+>", " ", raw_summary).strip()
                summary = re.sub(r"\s+", " ", summary)[:500]

                published = None
                for attr in ("published_parsed", "updated_parsed"):
                    val = getattr(entry, attr, None)
                    if val:
                        try:
                            published = datetime(*val[:6], tzinfo=timezone.utc)
                            break
                        except Exception:
                            pass

                if not title or not link:
                    continue
                if title in seen_titles:
                    continue
                if published and published < cutoff:
                    continue

                combined = (title + " " + summary).lower()
                if keywords and not any(kw in combined for kw in keywords):
                    continue

                seen_titles.add(title)
                articles.append({
                    "title": title,
                    "url": link,
                    "source": feed.feed.get("title", url),
                    "published": published.strftime("%Y-%m-%d %H:%M UTC") if published else "recent",
                    "summary": summary,
                })
        except Exception as e:
            print(f"  Warning: could not fetch {url}: {e}")

    return articles[:MAX_ARTICLES_PER_SECTION]


# ── Claude curation ───────────────────────────────────────────────────────────

def curate_section(client, section_key, articles):
    if not articles:
        return []

    section = SECTIONS[section_key]
    prompt = CURATION_PROMPT.format(
        section_title=section["title"].replace("&amp;", "&"),
        section_subtitle=section["subtitle"].replace("&amp;", "&"),
        articles_json=json.dumps(articles, indent=2),
    )

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        data = json.loads(raw)
        return data.get("stories", [])
    except json.JSONDecodeError as e:
        print(f"  Error parsing Claude response for {section_key}: {e}")
        return []
    except Exception as e:
        print(f"  Error curating {section_key}: {e}")
        return []


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_story(story, is_lead):
    headline = story.get("headline", "Untitled")
    source = story.get("source", "")
    url = story.get("url", "#")
    summary = story.get("summary", "")
    why = story.get("why_it_matters", "")
    lead_class = " story--lead" if is_lead else ""

    return f"""      <article class="story{lead_class}">
        <h3 class="story-headline"><a href="{url}" target="_blank" rel="noopener noreferrer">{headline}</a></h3>
        <p class="story-meta">{source}</p>
        <p class="story-summary">{summary}</p>
        <p class="why-it-matters"><span class="wim-label">Why it matters —</span> {why}</p>
      </article>"""


def render_section(section_key, stories):
    section = SECTIONS[section_key]
    if stories:
        stories_html = "\n".join(
            render_story(s, is_lead=(i == 0)) for i, s in enumerate(stories)
        )
    else:
        stories_html = '      <p class="no-stories">No significant new stories found for this section in this edition.</p>'

    return f"""
  <section class="news-section" id="{section_key}">
    <div class="section-header">
      <h2 class="section-title">{section["title"]}</h2>
      <span class="section-subtitle">{section["subtitle"]}</span>
    </div>
    <div class="stories">
{stories_html}
    </div>
  </section>"""


def render_full_page(edition_date, sections_html, css_path="style.css"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>The Daily Briefing — {edition_date}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:opsz,ital,wght@8..60,0,300;8..60,0,400;8..60,0,600;8..60,1,400&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="{css_path}" />
</head>
<body>
  <header class="masthead">
    <div class="masthead-topbar">
      <span class="topbar-left"><a href="archive.html">Past Editions</a></span>
      <span class="topbar-right">{edition_date}</span>
    </div>
    <div class="masthead-name-block">
      <div class="masthead-rule-top"></div>
      <h1 class="pub-name">The Daily Briefing</h1>
      <div class="masthead-rule-mid"></div>
      <p class="pub-tagline">&ldquo;Curated intelligence across four subjects&rdquo;</p>
      <div class="masthead-rule-bottom"></div>
    </div>
    <nav class="section-nav">
      <a href="#world_news">World News</a>
      <a href="#middle_east">The Middle East</a>
      <a href="#defense_security">Defense &amp; Security</a>
      <a href="#law_courts">Law &amp; Courts</a>
      <a href="#aviation">Aviation</a>
      <a href="#us_politics">U.S. Politics</a>
    </nav>
  </header>

  <main class="content">
{sections_html}
  </main>

  <footer class="site-footer">
    <div class="footer-rule"></div>
    <p class="footer-text">
      The Daily Briefing is generated each morning using curated RSS feeds and the Claude AI API.
      All stories link to their original sources; no full articles are reproduced.
    </p>
    <p class="footer-text"><a href="archive.html">Browse the archive</a></p>
  </footer>
</body>
</html>"""


def render_archive_page(editions):
    sorted_editions = sorted(editions, key=lambda x: x["date"], reverse=True)
    rows = "\n".join(
        f'      <li class="archive-item"><a href="editions/{e["filename"]}">{e["display_date"]}</a></li>'
        for e in sorted_editions
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Archive — The Daily Briefing</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:opsz,ital,wght@8..60,0,300;8..60,0,400;8..60,0,600;8..60,1,400&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="masthead">
    <div class="masthead-topbar">
      <span class="topbar-left"><a href="index.html">&larr; Latest Edition</a></span>
      <span class="topbar-right">Archive</span>
    </div>
    <div class="masthead-name-block">
      <div class="masthead-rule-top"></div>
      <h1 class="pub-name">The Daily Briefing</h1>
      <div class="masthead-rule-mid"></div>
      <p class="pub-tagline">&ldquo;Curated intelligence across four subjects&rdquo;</p>
      <div class="masthead-rule-bottom"></div>
    </div>
  </header>
  <main class="content">
    <section class="archive-section">
      <h2 class="archive-heading">Past Editions</h2>
      <ul class="archive-list">
{rows}
      </ul>
    </section>
  </main>
  <footer class="site-footer">
    <div class="footer-rule"></div>
    <p class="footer-text">The Daily Briefing — updated each morning.</p>
    <p class="footer-text"><a href="index.html">Return to latest edition</a></p>
  </footer>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Error: ANTHROPIC_API_KEY environment variable is not set.\n"
                         "Set it with: export ANTHROPIC_API_KEY='your-key-here'")

    client = anthropic.Anthropic(api_key=api_key)

    today = datetime.now(timezone.utc)
    edition_date = f"{today.strftime('%B')} {today.day}, {today.year}"
    filename_date = today.strftime("%Y-%m-%d")

    script_dir = Path(__file__).parent
    docs_dir = script_dir.parent / "docs"
    editions_dir = docs_dir / "editions"
    editions_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  The Daily Briefing — {edition_date}")
    print(f"{'='*55}\n")

    all_sections_html = ""

    for section_key, section_cfg in SECTIONS.items():
        print(f"[{section_cfg['title'].replace('&amp;', '&')}]")
        print(f"  Fetching from {len(section_cfg['feeds'])} feed(s)...")
        articles = fetch_articles(section_cfg["feeds"], section_cfg["keywords"])
        print(f"  Found {len(articles)} candidate articles")

        if articles:
            print(f"  Sending to Claude for curation...")
            stories = curate_section(client, section_key, articles)
            print(f"  Selected {len(stories)} stories")
        else:
            print(f"  No articles found — section will be empty")
            stories = []

        all_sections_html += render_section(section_key, stories)
        print()

    # Write this edition's archive file
    edition_html = render_full_page(edition_date, all_sections_html, css_path="../style.css")
    edition_file = editions_dir / f"{filename_date}.html"
    edition_file.write_text(edition_html, encoding="utf-8")
    print(f"Wrote: docs/editions/{filename_date}.html")

    # Update index.html
    index_html = render_full_page(edition_date, all_sections_html, css_path="style.css")
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")
    print("Updated: docs/index.html")

    # Rebuild archive
    editions = []
    for f in editions_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].html"):
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d")
            editions.append({
                "date": f.stem,
                "filename": f.name,
                "display_date": f"{d.strftime('%B')} {d.day}, {d.year}",
            })
        except ValueError:
            continue

    archive_html = render_archive_page(editions)
    (docs_dir / "archive.html").write_text(archive_html, encoding="utf-8")
    print("Updated: docs/archive.html")

    print(f"\nDone. Edition ready: {edition_date}\n")


if __name__ == "__main__":
    main()
