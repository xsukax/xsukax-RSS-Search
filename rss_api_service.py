#!/usr/bin/env python3
import concurrent.futures as futures
import sqlite3
import time
import unicodedata
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import feedparser
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

UA = "xsukax-RSS-Search/1.0"
TIMEOUT = 10
DB_FILE = "feeds.db"

app = FastAPI(title="xsukax RSS Search API", version="1.0")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

class FeedRequest(BaseModel):
    url: str

class SearchRequest(BaseModel):
    keywords: str
    field: str = "both"
    mode: str = "any"
    max_results: int = 0

class Feed(BaseModel):
    id: int
    url: str

class ValidateRequest(BaseModel):
    url: str

class ValidationResponse(BaseModel):
    valid: bool
    title: Optional[str] = None
    description: Optional[str] = None
    entry_count: int = 0
    error: Optional[str] = None

class SearchResult(BaseModel):
    title: str
    link: str
    summary: str
    source: str
    date: float
    date_str: str

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY, 
            url TEXT UNIQUE NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_feeds() -> List[Feed]:
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT id, url FROM feeds ORDER BY id").fetchall()
    conn.close()
    return [Feed(id=r[0], url=r[1]) for r in rows]

def add_feed(url: str) -> Feed:
    conn = sqlite3.connect(DB_FILE)
    try:
        cursor = conn.execute("INSERT INTO feeds (url) VALUES (?)", (url,))
        feed_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return Feed(id=feed_id, url=url)
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Feed already exists")

def delete_feed(feed_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if not affected:
        raise HTTPException(404, "Feed not found")

def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold() if text else ""

def parse_keywords(raw: str) -> List[str]:
    return [
        normalize(k.strip()) 
        for k in raw.replace("\n", ",").split(",") 
        if k.strip()
    ]

def matches(text: str, keywords: List[str], mode: str) -> bool:
    nt = normalize(text)
    hits = [kw in nt for kw in keywords]
    return any(hits) if mode == "any" else all(hits)

def get_field_text(entry: dict, field: str) -> str:
    title = entry.get("title", "")
    summary = entry.get("summary", "") or entry.get("description", "")
    if field == "title":
        return title
    elif field == "description":
        return summary
    else:
        return f"{title} {summary}"

def fetch_feed(url: str):
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception:
        return {"entries": []}

def get_entry_date(entry: dict) -> float:
    for key in ("published_parsed", "updated_parsed"):
        if entry.get(key):
            try:
                return time.mktime(entry[key])
            except Exception:
                pass
    return 0.0

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/feeds")
def list_feeds():
    return {"feeds": get_feeds()}

@app.post("/validate")
def validate_feed(req: ValidateRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL format")
    
    try:
        parsed = fetch_feed(url)
        if not parsed or "entries" not in parsed:
            raise HTTPException(400, "Invalid feed format")
        
        feed_info = parsed.get("feed", {})
        entry_count = len(parsed.get("entries", []))
        
        if entry_count == 0:
            raise HTTPException(400, "Feed contains no entries")
        
        return ValidationResponse(
            valid=True,
            title=feed_info.get("title", ""),
            description=feed_info.get("description", ""),
            entry_count=entry_count
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Feed validation failed: {str(e)}")

@app.post("/feeds")
def create_feed(req: FeedRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")
    
    feed = add_feed(url)
    return {"message": "Feed added", "feed": feed}

@app.delete("/feeds/{feed_id}")
def remove_feed(feed_id: int):
    delete_feed(feed_id)
    return {"message": "Feed deleted"}

@app.post("/search")
def search(req: SearchRequest):
    feeds = get_feeds()
    if not feeds:
        raise HTTPException(400, "No feeds configured")
    
    keywords = parse_keywords(req.keywords)
    if not keywords:
        raise HTTPException(400, "No keywords provided")
    
    urls = [f.url for f in feeds]
    
    with futures.ThreadPoolExecutor(max_workers=10) as executor:
        parsed_feeds = list(executor.map(fetch_feed, urls))
    
    results = []
    seen_links = set()
    failed_feeds = []
    
    for i, parsed in enumerate(parsed_feeds):
        if not parsed.get("entries"):
            failed_feeds.append(urls[i])
            continue
        
        for entry in parsed["entries"]:
            text = get_field_text(entry, req.field)
            if not text or not matches(text, keywords, req.mode):
                continue
            
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue
            
            seen_links.add(link)
            
            source = ""
            try:
                source = urlparse(link).netloc
            except Exception:
                pass
            
            date_epoch = get_entry_date(entry)
            date_str = (
                datetime.fromtimestamp(date_epoch).strftime('%b %d, %Y') 
                if date_epoch else ""
            )
            
            results.append(SearchResult(
                title=entry.get("title", ""),
                link=link,
                summary=entry.get("summary", "")[:300],
                source=source,
                date=date_epoch,
                date_str=date_str
            ))
    
    results.sort(key=lambda x: x.date, reverse=True)
    
    if req.max_results > 0:
        results = results[:req.max_results]
    
    return {
        "results": results,
        "total_feeds": len(feeds),
        "failed_feeds": failed_feeds,
        "search_params": {
            "keywords": req.keywords,
            "field": req.field,
            "mode": req.mode,
            "max_results": req.max_results
        },
        "generated_at": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    init_db()
    print("Starting xsukax RSS Search API...")
    print("Access at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)