#!/usr/bin/env python3
"""
Warrnambool Camera Club - MyPhotoClub public competition importer.

Initial run:
    python wcc_importer.py --initial

Monthly update:
    python wcc_importer.py

Outputs:
    data/photos.json       Regular competition images for member galleries
    data/ioty.json         IOTY award/placegetter images only
    data/processed.json    Competition-result posts already imported
    data/review.json       Entries that could not be parsed confidently
    data/member_ids.json   Learned CloudFront folder ID -> member mapping
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://warrnambool.myphotoclub.com.au/"
LISTING_PAGES = [
    BASE_URL,
    urljoin(BASE_URL, "page/2/"),
    urljoin(BASE_URL, "page/3/"),
    urljoin(BASE_URL, "page/4/"),
]
DATA_DIR = Path(__file__).resolve().parent.parent / "site" / "data"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
REQUEST_DELAY = 0.6
MAX_RETRIES = 3

# Known names give the importer a safe starting point.  The importer then learns
# the CloudFront numeric folder used by each photographer and can use that mapping
# for other entries by the same member.
KNOWN_MEMBERS = [
    "Andrew Iverach",
    "Barry Allen",
    "Bob Artis",
    "Chandika Isuru Lakmal Kumarage Don",
    "Craig Homberg",
    "Debbie Iverach",
    "Graham Dixon",
    "Jason Carter",
    "Lyn McConnell",
    "Mark Wishart",
    "Mark Kirby",
    "Phillip Morris",
    "Richard Conway",
    "Stan McCullagh",
    "Tania Jacobson",
    "Vivian Carter",
]

RESULT_MARKERS = [
    "1st Place", "2nd Place", "3rd Place",
    "First Place", "Second Place", "Third Place",
    "Highly Commended", "Honourable Mention", "Honorable Mention",
    "Commended", "Merit", "Accepted",
]

RESULT_RE = re.compile(
    r"\b(" + "|".join(re.escape(x) for x in sorted(RESULT_MARKERS, key=len, reverse=True)) + r")\b",
    re.I,
)
RESULT_POST_RE = re.compile(r"^\s*Results for competitions in\s+", re.I)
IOTY_RE = re.compile(r"\b(image\s+of\s+the\s+year|ioty)\b", re.I)
CLOUDFRONT_RE = re.compile(r"d1yqbttab18pa1\.cloudfront\.net", re.I)
FOLDER_RE = re.compile(r"d1yqbttab18pa1\.cloudfront\.net/(\d+)/")
ENTRY_COUNT_RE = re.compile(r"There were\s+(\d+)\s+entries", re.I)
DATE_RE = re.compile(
    r"\bon\s+(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s+(\d{4})\b",
    re.I,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
    temp.replace(path)


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" |")


def normalise_image_url(src: str, page_url: str) -> str:
    src = urljoin(page_url, src)
    # MyPhotoClub's public result pages normally use -small.jpg.  Preserve
    # whatever valid CDN URL the site supplied rather than inventing one.
    return src


def large_url(small_url: str) -> str:
    return re.sub(r"-small(\.[A-Za-z0-9]+)(?:\?.*)?$", r"-large\1", small_url)


def cloudfront_folder(url: str) -> str | None:
    m = FOLDER_RE.search(url)
    return m.group(1) if m else None


def is_ioty(name: str) -> bool:
    return bool(IOTY_RE.search(name or ""))


def is_ioty_award(result: str) -> bool:
    # The agreed WCC rule: normal IOTY entrants are not duplicated.  Only
    # placegetters/awards are retained in the separate IOTY collection.
    return clean_text(result).lower() != "accepted"


def fetch(session: requests.Session, url: str, *, allow_missing: bool = False) -> tuple[str | None, requests.Response | None]:
    """Fetch a page using normal browser-like headers and diagnostics.

    Listing pages occasionally behave differently for automated clients.  We
    therefore use realistic browser headers, follow redirects, retry transient
    failures, and report the final URL/status/title rather than failing silently.
    """
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=30, allow_redirects=True)
            ctype = r.headers.get("Content-Type", "")
            title = ""
            if "html" in ctype.lower() and r.text:
                soup = BeautifulSoup(r.text, "html.parser")
                if soup.title:
                    title = clean_text(soup.title.get_text(" ", strip=True))
            print(f"  HTTP {r.status_code} | final: {r.url}" + (f" | title: {title}" if title else ""))

            if r.status_code == 404 and allow_missing:
                # MyPhotoClub currently returns HTTP 404 for some older paginated
                # listing URLs even though the response body contains the real,
                # browser-renderable archive page. Browsers display that HTML;
                # therefore listing discovery must inspect the body instead of
                # treating the status code alone as proof that the page is absent.
                body = r.text or ""
                if body.strip():
                    print("  NOTE: HTTP 404 returned with HTML body; parsing the body for result posts.")
                    time.sleep(REQUEST_DELAY)
                    return body, r
                return None, r
            r.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return r.text, r
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                wait = attempt * 1.5
                print(f"  Request failed ({exc}); retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                break
    raise last_error


def discover_result_posts(session: requests.Session, pages: list[str]) -> tuple[list[dict], list[dict]]:
    found: dict[str, dict] = {}
    diagnostics: list[dict] = []
    for page_url in pages:
        print(f"Scanning listing: {page_url}")
        try:
            html, response = fetch(session, page_url, allow_missing=True)
        except Exception as exc:
            print(f"  ERROR: could not retrieve listing page: {exc}", file=sys.stderr)
            diagnostics.append({
                "page": page_url,
                "status": "error",
                "error": str(exc),
                "checkedAt": now_iso(),
            })
            continue

        status = response.status_code if response is not None else None
        final_url = response.url if response is not None else page_url
        diagnostics.append({
            "page": page_url,
            "status": status,
            "finalUrl": final_url,
            "htmlBodyParsed": bool(html),
            "checkedAt": now_iso(),
        })

        if html is None:
            print("  Listing returned 404 with no usable HTML body. Continuing.")
            continue

        soup = BeautifulSoup(html, "html.parser")
        page_hits = 0
        for a in soup.find_all("a", href=True):
            text = clean_text(a.get_text(" ", strip=True))
            href = urljoin(final_url, a["href"])
            if RESULT_POST_RE.search(text):
                found[href] = {"url": href, "title": text, "listing_page": page_url}
                page_hits += 1
        print(f"  Result posts found on this listing: {page_hits}")
    return list(found.values()), diagnostics


def post_title(soup: BeautifulSoup, fallback: str) -> str:
    for selector in ("h1", "article h2", ".entry-title", "h2"):
        node = soup.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if RESULT_POST_RE.search(text):
                return RESULT_POST_RE.sub("", text).strip()
    text = RESULT_POST_RE.sub("", fallback or "").strip()
    return text or "Unknown competition"


def post_date(soup: BeautifulSoup) -> str | None:
    time_node = soup.find("time")
    if time_node:
        dt = time_node.get("datetime")
        if dt:
            return dt
    text = clean_text(soup.get_text(" ", strip=True))
    m = DATE_RE.search(text)
    if m:
        try:
            return datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()
        except ValueError:
            pass
    return None


def expected_entry_count(soup: BeautifulSoup) -> int | None:
    m = ENTRY_COUNT_RE.search(clean_text(soup.get_text(" ", strip=True)))
    return int(m.group(1)) if m else None


def candidate_container(img):
    """
    Find the smallest ancestor that contains the result text belonging to this
    image.  MyPhotoClub layouts have changed over time, so this deliberately
    avoids relying on one CSS class.
    """
    node = img
    best = None
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = clean_text(node.get_text(" ", strip=True))
        if RESULT_RE.search(text):
            if len(text) <= 700:
                best = node
                # Prefer common per-entry containers.
                if getattr(node, "name", "") in {"td", "li", "figure", "article"}:
                    break
            elif best is not None:
                break
    return best


def text_for_image(img) -> str:
    node = candidate_container(img)
    if node is None:
        return ""
    text = clean_text(node.get_text(" ", strip=True))
    # Some templates include literal "Thumbnail" link text.
    text = re.sub(r"\bThumbnail\b", "", text, flags=re.I)
    return clean_text(text)


def split_result(raw_text: str) -> tuple[str, str, str] | None:
    """
    Returns (left_part, result, section).  left_part is still title + member.
    """
    m = RESULT_RE.search(raw_text)
    if not m:
        return None
    left = clean_text(raw_text[:m.start()].rstrip("–—- "))
    result = clean_text(m.group(1))
    right = clean_text(raw_text[m.end():].lstrip("–—- "))
    if not left:
        return None
    return left, result, right


def member_from_left(left: str, known_members: list[str]) -> tuple[str | None, str | None]:
    # Longest names first prevents suffix ambiguity.
    for member in sorted(known_members, key=len, reverse=True):
        if re.search(r"(?:^|\s)" + re.escape(member) + r"\s*$", left, re.I):
            title = re.sub(r"(?:^|\s)" + re.escape(member) + r"\s*$", "", left, flags=re.I)
            return member, clean_text(title)
    return None, None


def collect_raw_entries(soup: BeautifulSoup, page_url: str) -> list[dict]:
    entries = []
    seen_urls = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if not src or not CLOUDFRONT_RE.search(src):
            continue
        src = normalise_image_url(src, page_url)
        if src in seen_urls:
            continue
        raw_text = text_for_image(img)
        parsed = split_result(raw_text)
        if not parsed:
            continue
        left, result, section = parsed
        entries.append({
            "image": src,
            "largeImage": large_url(src),
            "folderId": cloudfront_folder(src),
            "rawText": raw_text,
            "left": left,
            "result": result,
            "section": section,
        })
        seen_urls.add(src)
    return entries


def parse_post(session, info: dict, member_ids: dict[str, str]) -> tuple[dict, list[dict], list[dict]]:
    url = info["url"]
    print(f"Importing result: {url}")
    html, _response = fetch(session, url)
    if html is None:
        raise RuntimeError("Result post unexpectedly returned no HTML")
    soup = BeautifulSoup(html, "html.parser")
    competition = post_title(soup, info.get("title", ""))
    date = post_date(soup)
    expected = expected_entry_count(soup)
    raw_entries = collect_raw_entries(soup, url)

    # First pass: known member names. Learn folder ID -> member.
    known_members = list(KNOWN_MEMBERS)
    known_members.extend(x for x in member_ids.values() if x not in known_members)
    parsed = []
    unresolved = []

    for e in raw_entries:
        member, title = member_from_left(e["left"], known_members)
        if member and e["folderId"]:
            existing = member_ids.get(e["folderId"])
            if existing and existing != member:
                unresolved.append({
                    "reason": "CloudFront folder maps to conflicting member names",
                    "competition": competition,
                    "post": url,
                    **e,
                    "detectedMember": member,
                    "existingMember": existing,
                })
                continue
            member_ids[e["folderId"]] = member
        e["member"] = member
        e["title"] = title
        parsed.append(e)

    # Second pass: use a learned folder mapping for entries whose title/member
    # string could not be split from the known-name list.
    final = []
    for e in parsed:
        if not e["member"] and e["folderId"] in member_ids:
            member = member_ids[e["folderId"]]
            member2, title = member_from_left(e["left"], [member])
            if member2:
                e["member"] = member2
                e["title"] = title

        if not e["member"] or not e["title"]:
            unresolved.append({
                "reason": "Could not separate photographer name from image title",
                "competition": competition,
                "post": url,
                **e,
            })
            continue

        final.append({
            "member": e["member"],
            "title": e["title"],
            "competition": competition,
            "competitionDate": date,
            "section": e["section"],
            "result": e["result"],
            "image": e["image"],
            "largeImage": e["largeImage"],
            "folderId": e["folderId"],
            "sourcePost": url,
        })

    meta = {
        "title": competition,
        "url": url,
        "date": date,
        "expectedEntries": expected,
        "cdnEntriesFound": len(raw_entries),
        "entriesImported": len(final),
        "entriesForReview": len(unresolved),
        "processedAt": now_iso(),
    }
    return meta, final, unresolved


def stable_key(photo: dict) -> str:
    # We intentionally do NOT use this to deduplicate IOTY resubmissions against
    # monthly entries.  It only prevents importing the exact same CDN asset twice.
    return "|".join([
        photo.get("sourcePost", ""),
        photo.get("image", ""),
        photo.get("member", ""),
    ])


def sort_photos(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda x: (
            x.get("member", "").casefold(),
            x.get("competitionDate") or "",
            x.get("competition", "").casefold(),
            x.get("title", "").casefold(),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--initial",
        action="store_true",
        help="Scan all four known listing pages. Without this flag, scan page 1 only.",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Reprocess result posts even if already present in processed.json.",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    photos_path = DATA_DIR / "photos.json"
    ioty_path = DATA_DIR / "ioty.json"
    processed_path = DATA_DIR / "processed.json"
    review_path = DATA_DIR / "review.json"
    member_ids_path = DATA_DIR / "member_ids.json"

    photos = read_json(photos_path, [])
    ioty = read_json(ioty_path, [])
    processed = read_json(processed_path, {"posts": {}})
    review = read_json(review_path, [])
    member_ids = read_json(member_ids_path, {})

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    })

    pages = LISTING_PAGES if args.initial else [BASE_URL]
    posts, listing_diagnostics = discover_result_posts(session, pages)
    posts.sort(key=lambda x: x["url"])
    print(f"Found {len(posts)} result post(s) on the listing page(s).")

    existing_photo_keys = {stable_key(x) for x in photos}
    existing_ioty_keys = {stable_key(x) for x in ioty}
    imported_posts = 0
    new_regular = 0
    new_ioty = 0
    new_review = []

    for info in posts:
        if not args.reprocess and info["url"] in processed.get("posts", {}):
            print(f"Skipping already processed: {info['url']}")
            continue

        try:
            meta, entries, unresolved = parse_post(session, info, member_ids)
        except Exception as exc:
            print(f"ERROR importing {info['url']}: {exc}", file=sys.stderr)
            new_review.append({
                "reason": "Post import failed",
                "post": info["url"],
                "error": str(exc),
                "recordedAt": now_iso(),
            })
            continue

        # If MyPhotoClub says the post has N entries but our HTML parser found
        # fewer CDN records, do not silently mark it complete.
        expected = meta.get("expectedEntries")
        found = meta.get("cdnEntriesFound", 0)
        complete_enough = expected is None or found >= expected

        for photo in entries:
            if is_ioty(photo["competition"]):
                if is_ioty_award(photo["result"]):
                    key = stable_key(photo)
                    if key not in existing_ioty_keys:
                        ioty.append(photo)
                        existing_ioty_keys.add(key)
                        new_ioty += 1
            else:
                key = stable_key(photo)
                if key not in existing_photo_keys:
                    photos.append(photo)
                    existing_photo_keys.add(key)
                    new_regular += 1

        new_review.extend(unresolved)

        if complete_enough:
            processed.setdefault("posts", {})[info["url"]] = meta
            imported_posts += 1
        else:
            new_review.append({
                "reason": "Entry-count validation failed; post not marked processed",
                "competition": meta["title"],
                "post": info["url"],
                "expectedEntries": expected,
                "cdnEntriesFound": found,
                "recordedAt": now_iso(),
            })

    processed["lastRun"] = now_iso()
    processed["mode"] = "initial" if args.initial else "monthly"
    processed["listingDiagnostics"] = listing_diagnostics

    write_json(photos_path, sort_photos(photos))
    write_json(ioty_path, sort_photos(ioty))
    write_json(processed_path, processed)
    write_json(member_ids_path, dict(sorted(member_ids.items())))
    if new_review:
        review.extend(new_review)
    write_json(review_path, review)

    print()
    print("Import complete")
    print(f"  Result posts newly processed : {imported_posts}")
    print(f"  Regular images added         : {new_regular}")
    print(f"  IOTY award images added      : {new_ioty}")
    print(f"  New review records           : {len(new_review)}")
    print(f"  Total regular images         : {len(photos)}")
    print(f"  Total IOTY award images      : {len(ioty)}")
    print()
    print(f"Data written to: {DATA_DIR}")
    if new_review:
        print("IMPORTANT: review data/review.json before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
