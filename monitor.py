"""Stock news agent: fetch headlines -> Claude scores impact -> ntfy push to phone."""
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import quote_plus

import anthropic
import feedparser
import requests

# ---- Settings you can change ----------------------------------------------
WATCHLIST = {
    "META": "Meta Platforms",
    "GOOGL": "Alphabet Google",
    "NVDA": "Nvidia",
    "AAPL": "Apple Inc",
    "AMZN": "Amazon",
    "MSFT": "Microsoft",
}
THRESHOLD = 7            # alert if Claude's impact score is >= this (1-10)
MODEL = "claude-haiku-4-5-20251001"
MAX_HEADLINES_PER_RUN = 60
SEEN_FILE = Path("seen.json")
# ----------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You screen financial news for an investor watching: {', '.join(WATCHLIST.values())}.
For each headline, rate from 1-10 how likely it is to move that company's stock price materially.
High (8-10): earnings/guidance surprises, major lawsuits or regulatory rulings, M&A,
large contracts, big product or chip announcements, executive departures, outages/recalls, major analyst rating changes.
Medium (5-7): notable but incremental company news.
Low (1-4): opinion pieces, "should you buy" articles, listicles, routine price-target notes, general market chatter.
Be strict: most headlines should score low.
Respond ONLY with a JSON array, no other text:
[{{"id": <int>, "ticker": "<main ticker>", "score": <1-10>, "reason": "<max 15 words>"}}]"""


def fetch_headlines():
    items = {}
    for ticker, name in WATCHLIST.items():
        feeds = [
            f"https://news.google.com/rss/search?q={quote_plus(name + ' stock')}+when:1d&hl=en-US&gl=US&ceid=US:en",
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        ]
        for url in feeds:
            try:
                for e in feedparser.parse(url).entries[:15]:
                    title = e.get("title", "").strip()
                    if not title:
                        continue
                    key = hashlib.sha1(re.sub(r"\W+", "", title.lower()).encode()).hexdigest()
                    items.setdefault(key, {"title": title, "link": e.get("link", ""), "ticker": ticker})
            except Exception as exc:
                print(f"Feed error for {ticker}: {exc}")
    return items


def score(new_items):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    keys = list(new_items.keys())
    lines = [f"{i}: [{new_items[k]['ticker']}] {new_items[k]['title']}" for i, k in enumerate(keys)]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )
    text = resp.content[0].text
    match = re.search(r"\[.*\]", text, re.S)
    results = json.loads(match.group(0)) if match else []
    return keys, results


def notify(topic, item, ticker, sc, reason):
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=reason.encode("utf-8"),
        headers={
            "Title": f"{ticker} ({sc}/10): {item['title'][:80]}".encode("ascii", "ignore").decode(),
            "Priority": "high" if sc >= 9 else "default",
            "Tags": "chart_with_upwards_trend",
            "Click": item["link"],
        },
        timeout=15,
    )


def main():
    topic = os.environ["NTFY_TOPIC"]
    items = fetch_headlines()

    first_run = not SEEN_FILE.exists()
    seen = set(json.loads(SEEN_FILE.read_text())) if not first_run else set()

    new_items = {k: v for k, v in items.items() if k not in seen}
    if first_run:
        print(f"First run: marking {len(new_items)} headlines as seen, no alerts.")
        SEEN_FILE.write_text(json.dumps(list(new_items.keys())))
        return

    batch = dict(list(new_items.items())[:MAX_HEADLINES_PER_RUN])
    print(f"{len(new_items)} new headlines, scoring {len(batch)}.")
    if batch:
        keys, results = score(batch)
        for r in results:
            try:
                if int(r["score"]) >= THRESHOLD:
                    notify(topic, batch[keys[int(r["id"])]], r.get("ticker", "?"), int(r["score"]), r.get("reason", ""))
                    print("Alert:", batch[keys[int(r["id"])]]["title"])
            except (KeyError, IndexError, ValueError) as exc:
                print("Skipping bad result:", exc)

    seen.update(batch.keys())
    SEEN_FILE.write_text(json.dumps(list(seen)[-3000:]))


if __name__ == "__main__":
    main()
To fix it:
In your repo, open monitor.py
