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

