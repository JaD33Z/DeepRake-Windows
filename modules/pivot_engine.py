# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# pivot_engine.py — Self-expanding dork pivoter for DEEP-RAKE
# License: MIT
#
# PURPOSE
# -------
# Adds "self-pivot intelligence" to your search harvester (DEEP-RAKE or similar).
# Given seed queries + search results, it:
#   1) Extracts salient keywords/phrases from titles/snippets/URLs (no 3rd‑party deps).
#   2) Generates new, high-signal dorks using smart templates (site scoping, filetypes,
#      directory listings, multilingual pivots).
#   3) Deduplicates via a rolling JSONL state to prevent runaway query bloat.
#   4) Outputs a clean "next_queries.txt" you can immediately feed back into your crawler.
#
# DROP-IN INTEGRATION
# -------------------
# Option A (CLI, simplest):
#     # After a crawl, export your results to JSONL (one result per line):
#     # Each line must contain: {"title": "...", "snippet": "...", "url": "https://...", "site": "domain.tld"}
#     python pivot_engine.py \
#         --results ./out/search_results.jsonl \
#         --output ./out/next_queries.txt \
#         --state ./out/pivot_state.jsonl \
#         --max-new 150
#
# Option B (Library use):
#     from pivot_engine import PivotEngine, load_results_jsonl
#     engine = PivotEngine(state_path="./out/pivot_state.jsonl")
#     results = load_results_jsonl("./out/search_results.jsonl")
#     next_queries = engine.propose_queries(results, max_new=150)
#     engine.write_queries(next_queries, "./out/next_queries.txt")
#
# FILE FIELDS
# -----------
# - results jsonl fields per line (REQUIRED):
#     title: str       -> page title (string; allow empty)
#     snippet: str     -> SERP snippet / summary (string; allow empty)
#     url: str         -> absolute URL (used for domain inference)
#     site: str        -> domain-only if you have it (else leave empty; we infer)
#
# CONFIG / TUNING (edit DEFAULTS below if desired)
# -----------------------------------------------
# - STOPWORDS: in-module set; extend to your needs.
# - FILETYPES: prioritize pdf, doc, ppt, xls; add others if helpful.
# - TEMPLATES: see _TEMPLATES; tweak for your mission profile.
# - LANGUAGE PIVOTS: optional, controlled via flags.
#
# SAFETY / ETHICS
# ---------------
# Use responsibly. Respect robots.txt, rate limits, and the law. This module is for
# OSINT research and academic exploration only.
# """
#


# pivot_engine.py — DeepRake with Harvest Feed API support
# Author: JonD
# License: MIT

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ------------------------------
# Defaults & Constants
# ------------------------------

_STOPWORDS: Set[str] = {
    "a","an","and","the","or","for","to","of","in","on","by","with","at","from","as","is","are",
    "be","this","that","it","its","into","over","about","between","within","without","across",
    "we","you","they","their","our","your","not","no","yes","but","if","then","than","such",
    "can","may","might","also","using","use","used","via","new","pdf","doc","ppt","xls","data",
    "report","paper","study","results","based","analysis","research","site","filetype","index"
}

_FILETYPES: Tuple[str, ...] = ("pdf","doc","docx","ppt","pptx","xls","xlsx")

_TEMPLATES = [
    lambda kw, site, ft: f'site:.edu "{kw}" filetype:{ft}',
    lambda kw, site, ft: f'site:.org "{kw}" filetype:{ft}',
    lambda kw, site, ft: f'site:.gov "{kw}" filetype:{ft}',
    lambda kw, site, ft: f'site:.mil "{kw}" filetype:{ft}',
    lambda kw, site, ft: f'intitle:"index of" "{kw}"',
    lambda kw, site, ft: f'intitle:"index of" "{kw}" { "site:"+site if site else ""}'.strip(),
    lambda kw, site, ft: f'"{kw}" { "site:"+site if site else ""} filetype:{ft}'.strip(),
    lambda kw, site, ft: f'"{kw}" "declassified" filetype:{ft}',
]

_LANG_PIVOTS = {
    "de": ['"{kw}" site:.de filetype:pdf', '"geheimes wissen" "{kw}" filetype:pdf'],
    "es": ['"{kw}" site:.es filetype:pdf', '"conocimiento prohibido" "{kw}" filetype:pdf'],
    "it": ['"{kw}" site:.it filetype:pdf', '"conoscenza proibita" "{kw}" filetype:pdf'],
    "pt": ['"{kw}" site:.br filetype:pdf', '"conhecimento proibido" "{kw}" filetype:pdf'],
    "jp": ['"{kw}" site:.jp filetype:pdf', '"\u79d8\u5bc6\u306e\u77e5\u8b58" "{kw}" filetype:pdf'],
}

MAX_PHRASE_WORDS = 5
MIN_PHRASE_WORDS = 1
MAX_KEYWORDS_PER_ITEM = 6
MAX_TOTAL_NEW = 200

@dataclass
class SearchResult:
    title: str = ""
    snippet: str = ""
    url: str = ""
    site: str = ""

def _domain_from_url(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""

def _normalize_text(s: str) -> str:
    s = s or ""
    s = re.sub(r"[^0-9A-Za-z\u00C0-\u017F\u4E00-\u9FFF\u3040-\u30FF\u0E00-\u0E7F]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()

def _tokenize(s: str) -> List[str]:
    return [t for t in _normalize_text(s).split(" ") if t]

def _is_stop(token: str) -> bool:
    return (token in _STOPWORDS) or len(token) <= 2 or token.isnumeric()

def _extract_candidate_phrases(tokens: List[str]) -> List[str]:
    chunks, cur = [], []
    for tok in tokens:
        if _is_stop(tok):
            if cur:
                chunks.append(cur)
                cur = []
        else:
            cur.append(tok)
    if cur: chunks.append(cur)
    phrases = []
    for ch in chunks:
        if MIN_PHRASE_WORDS <= len(ch) <= MAX_PHRASE_WORDS:
            phrases.append(" ".join(ch))
        elif len(ch) > MAX_PHRASE_WORDS:
            for i in range(0, len(ch) - MAX_PHRASE_WORDS + 1):
                phrases.append(" ".join(ch[i:i+MAX_PHRASE_WORDS]))
    return phrases

def _score_phrases(phrases: List[str]) -> Dict[str, float]:
    counts = Counter(phrases)
    scores = {}
    for p, c in counts.items():
        length_bonus = min(len(p.split()), MAX_PHRASE_WORDS) / MAX_PHRASE_WORDS
        scores[p] = c * (1.0 + 0.5 * length_bonus)
    return scores

def _best_keywords(text: str, top_k: int = 8) -> List[str]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    phrases = _extract_candidate_phrases(tokens)
    if not phrases:
        return []
    scores = _score_phrases(phrases)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [p for p, _ in ranked[:top_k]]

def _unique(seq: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for s in seq:
        key = s.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(s.strip())
    return out

def load_results_jsonl(path: str) -> List[SearchResult]:
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            title = obj.get("title","") or ""
            snippet = obj.get("snippet","") or ""
            url = obj.get("url","") or ""
            site = obj.get("site","") or ""
            if not site and url:
                site = _domain_from_url(url)
            results.append(SearchResult(title=title, snippet=snippet, url=url, site=site))
    return results

class PivotEngine:
    def __init__(self, state_path: str):
        self.state_path = Path(state_path)
        self.seen_queries: Set[str] = set()
        self._load_state()

    def _load_state(self):
        if not self.state_path.exists():
            return
        with open(self.state_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    q = obj.get("q","")
                    if q:
                        self.seen_queries.add(q.lower())
                except json.JSONDecodeError:
                    continue

    def _append_state(self, queries: Sequence[str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "a", encoding="utf-8") as f:
            for q in queries:
                f.write(json.dumps({"q": q}, ensure_ascii=False) + "\n")

    def _gen_from_keywords(self, keywords: Sequence[str], site: str="") -> List[str]:
        return [tmpl(kw, site, ft) for kw in keywords for ft in _FILETYPES for tmpl in _TEMPLATES]

    def _lang_pivots(self, keywords: Sequence[str]) -> List[str]:
        return [pat.format(kw=kw) for kw in keywords for lang, pats in _LANG_PIVOTS.items() for pat in pats]

    def propose_queries(self, results: Sequence[SearchResult], max_new: int = 150, enable_lang_pivots: bool = True) -> List[str]:
        all_texts = []
        for r in results:
            text = " ".join(filter(None, [r.title, r.snippet]))
            kws = _best_keywords(text, top_k=MAX_KEYWORDS_PER_ITEM)
            if not kws:
                path_tokens = _tokenize(urllib.parse.urlparse(r.url or "").path)
                kws = [p for p in _extract_candidate_phrases(path_tokens)][:3]
            if kws:
                all_texts.append((kws, r.site))
        raw = []
        for kws, site in all_texts:
            raw.extend(self._gen_from_keywords(kws, site))
            if enable_lang_pivots:
                raw.extend(self._lang_pivots(kws))
        fresh = [q for q in _unique(raw) if q.lower() not in self.seen_queries]
        selected = fresh[:min(max_new, MAX_TOTAL_NEW)]
        self._append_state(selected)
        return selected

    @staticmethod
    def write_queries(queries: Sequence[str], output_path: str):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for q in queries:
                f.write(q.strip() + "\n")

# HARVEST FEED BLOCK
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/api/harvest_feed", methods=["GET"])
def harvest_feed():
    state_file = Path("out/pivot_state.jsonl")
    if not state_file.exists():
        return jsonify([])
    lines = state_file.read_text(encoding="utf-8").splitlines()
    queries = [json.loads(l).get("q", "") for l in lines if l.strip()]
    return jsonify(list(reversed(queries[-100:])))

def _cli(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Self-expanding dork pivot generator")
    p.add_argument("--results", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--max-new", type=int, default=150)
    p.add_argument("--no-lang", action="store_true")
    args = p.parse_args(argv)

    results = load_results_jsonl(args.results)
    engine = PivotEngine(state_path=args.state)
    next_queries = engine.propose_queries(results, max_new=args.max_new, enable_lang_pivots=not args.no_lang)
    PivotEngine.write_queries(next_queries, args.output)
    print(f"[pivot_engine] Proposed {len(next_queries)} new queries → {args.output}")
    return 0

if __name__ == "__main__":
    if "runserver" in sys.argv:
        app.run(debug=True, port=8000)
    else:
        raise SystemExit(_cli())
