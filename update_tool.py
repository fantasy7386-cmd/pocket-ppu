#!/usr/bin/env python3
"""
Pocket PPu Update Tool
======================
Add new PDF health education articles to the Pocket PPu database.

Usage:
  python3 update_tool.py --add "新檔案.pdf" --category "01_攝護腺癌"
  python3 update_tool.py --add "path/to/file.pdf" --category "03_膀胱癌"
  python3 update_tool.py --scan                    # scan for new PDFs in all folders
  python3 update_tool.py --list                    # list all articles in database
  python3 update_tool.py --remove art_042          # remove an article by ID
  python3 update_tool.py --rebuild                 # rebuild entire database from PDFs

Category folder names:
  01_攝護腺癌, 02_轉移性攝護腺癌, 03_膀胱癌, 04_尿路結石,
  05_泌尿道感染, 06_其他泌尿問題, 07_用藥資訊, 08_相關用書,
  09_攝護腺肥大, 10_攝護腺癌用藥, 11_轉移性攝護腺癌用藥,
  12_攝護腺癌專題系列, 13_攝護腺癌照護小卡
"""

import argparse
import json
import os
import re
import sys
import shutil
from datetime import datetime

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
PDF_DIR = "/Users/chengyangdata/tmua_health_download/pdfs"

CATEGORY_MAP = {
    "01_攝護腺癌": "prostate_cancer",
    "02_轉移性攝護腺癌": "metastatic_pc",
    "03_膀胱癌": "bladder_cancer",
    "04_尿路結石": "urolithiasis",
    "05_泌尿道感染": "uti",
    "06_其他泌尿問題": "other_uro",
    "07_用藥資訊": "medication_info",
    "08_相關用書": "related_books",
    "09_攝護腺肥大": "bph",
    "10_攝護腺癌用藥": "pc_medication",
    "11_轉移性攝護腺癌用藥": "mpc_medication",
    "12_攝護腺癌專題系列": "pc_series",
    "13_攝護腺癌照護小卡": "care_cards",
}

KEYWORD_PATTERNS = [
    r'\b(PSA|MRI|CT|PET|TURP|HIFU|BPH|LHRH|GnRH|ECOG)\b',
    r'\b(docetaxel|cabazitaxel|abiraterone|enzalutamide|bicalutamide)\b',
    r'\b(Gleason|PI-RADS|PHI|DEXA|DXA)\b',
    r'\b(Zytiga|Xtandi|Casodex|Urief|Xatral|AVODART)\b',
    r'\b(Harnalidge|Foxate|MINIRIN|Oxbu|Doxazosin)\b',
    r'(攝護腺癌|膀胱癌|腎臟癌|尿路結石|攝護腺肥大)',
    r'(荷爾蒙治療|化學治療|放射線治療|冷凍治療|免疫治療)',
    r'(骨轉移|淋巴結轉移|遠端轉移)',
    r'(達文西|機器手臂|腹腔鏡)',
    r'(凱格爾運動|提肛運動)',
    r'(醛固酮|皮質醇|睪固酮|雄性素)',
    r'(尿失禁|血尿|頻尿|夜尿|排尿困難)',
    r'(切片|切除術|根除性)',
    r'(健保給付|自費)',
    r'(副作用|禁忌症)',
]


# --- PDF Text Extraction ---
def get_pymupdf():
    """Try to import pymupdf from venv or system."""
    paths = [
        "/tmp/pdfenv/lib/python3.14/site-packages",
        "/tmp/pdfenv/lib/python3.13/site-packages",
        "/tmp/pdfenv/lib/python3.12/site-packages",
    ]
    for p in paths:
        if os.path.exists(p):
            sys.path.insert(0, p)
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        return None


def extract_text(filepath):
    """Extract text from a PDF file."""
    pymupdf = get_pymupdf()
    if not pymupdf:
        print("ERROR: pymupdf not available. Install it with:")
        print("  python3 -m venv /tmp/pdfenv && /tmp/pdfenv/bin/pip install pymupdf")
        sys.exit(1)

    try:
        doc = pymupdf.open(filepath)
        pages = []
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text")
            if text.strip():
                pages.append(text.strip())
        doc.close()

        combined = "\n\n".join(pages)
        combined = re.sub(r'\n{3,}', '\n\n', combined)
        combined = re.sub(r' {2,}', ' ', combined)

        if not combined.strip():
            print(f"  WARNING: PDF appears to be image-only (no extractable text).")
            print(f"  You may need to manually add the text content.")
            return "", 0

        return combined, len(pages)
    except Exception as e:
        print(f"  ERROR extracting text: {e}")
        return "", 0


def extract_title(filename):
    """Extract clean title from filename."""
    title = filename.replace(".pdf", "")
    title = re.sub(r'^\(?(PC|MPC|PCD)-?\d+\)?\s*', '', title)
    return title.strip(' -_') or filename.replace(".pdf", "")


def extract_keywords(text, title):
    """Extract medical keywords from text."""
    keywords = set()
    search_text = text + " " + title
    for pattern in KEYWORD_PATTERNS:
        for m in re.findall(pattern, search_text, re.IGNORECASE):
            keywords.add(m.strip())
    return sorted(keywords)


def find_related(articles, new_article):
    """Find related articles based on shared keywords."""
    kw_set = set(new_article["keywords"])
    related = []
    for other in articles:
        if other["id"] == new_article["id"]:
            continue
        overlap = len(kw_set & set(other["keywords"]))
        if overlap >= 2:
            related.append({"id": other["id"], "score": overlap})
    related.sort(key=lambda x: x["score"], reverse=True)
    return [r["id"] for r in related[:5]]


def next_article_id(data):
    """Get the next available article ID."""
    existing = [int(a["id"].replace("art_", "")) for a in data["articles"]]
    return f"art_{max(existing) + 1:03d}" if existing else "art_000"


# --- Database Operations ---
def load_data():
    """Load the JSON database."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    """Save the JSON database with backup."""
    # Backup
    backup = DATA_FILE + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(DATA_FILE, backup)
    print(f"  Backup saved: {os.path.basename(backup)}")

    # Update metadata
    data["total_articles"] = len(data["articles"])
    data["generated"] = datetime.now().strftime("%Y-%m-%d")

    # Rebuild glossary
    glossary = {}
    for article in data["articles"]:
        for kw in article.get("keywords", []):
            glossary.setdefault(kw, [])
            if article["id"] not in glossary[kw]:
                glossary[kw].append(article["id"])
    data["glossary"] = dict(sorted(glossary.items()))

    # Update category counts
    for cat in data["categories"]:
        cat_articles = [a["id"] for a in data["articles"] if a["category"] == cat["id"]]
        cat["articles"] = cat_articles
        cat["count"] = len(cat_articles)

    # Update related articles
    for article in data["articles"]:
        article["related"] = find_related(data["articles"], article)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(DATA_FILE) / 1024
    print(f"  Database saved: {data['total_articles']} articles, {size_kb:.0f} KB")


# --- Commands ---
def cmd_add(args):
    """Add a new PDF to the database."""
    pdf_path = args.add
    category = args.category

    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        sys.exit(1)

    if category not in CATEGORY_MAP:
        print(f"ERROR: Unknown category: {category}")
        print(f"Available categories:")
        for k in sorted(CATEGORY_MAP.keys()):
            print(f"  {k}")
        sys.exit(1)

    cat_id = CATEGORY_MAP[category]
    filename = os.path.basename(pdf_path)

    print(f"\n=== Adding: {filename} ===")
    print(f"  Category: {category} ({cat_id})")

    # Check for duplicates
    data = load_data()
    for a in data["articles"]:
        if a["filename"] == filename and a["category"] == cat_id:
            print(f"  ERROR: Article already exists: {a['title']} (ID: {a['id']})")
            sys.exit(1)

    # Extract text
    print(f"  Extracting text...")
    text, page_count = extract_text(pdf_path)

    if not text:
        print(f"  No text extracted. This PDF may be image-only.")
        ans = input("  Enter text manually? (y/n): ").strip().lower()
        if ans == 'y':
            print("  Paste text below (end with an empty line):")
            lines = []
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
            text = "\n".join(lines)
            page_count = 1
        else:
            print("  Skipped.")
            return

    title = extract_title(filename)
    keywords = extract_keywords(text, title)
    article_id = next_article_id(data)

    article = {
        "id": article_id,
        "title": title,
        "filename": filename,
        "category": cat_id,
        "text": text,
        "pages": page_count,
        "keywords": keywords,
        "related": [],
    }

    data["articles"].append(article)

    # Copy PDF to storage
    dest_dir = os.path.join(PDF_DIR, category)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    if not os.path.exists(dest_path) and os.path.abspath(pdf_path) != os.path.abspath(dest_path):
        shutil.copy2(pdf_path, dest_path)
        print(f"  PDF copied to: {dest_dir}/")

    save_data(data)

    print(f"\n  ADDED: {title}")
    print(f"  ID: {article_id}")
    print(f"  Pages: {page_count}")
    print(f"  Characters: {len(text):,}")
    print(f"  Keywords: {', '.join(keywords) if keywords else '(none)'}")


def cmd_scan(args):
    """Scan PDF folders for new files not yet in the database."""
    data = load_data()
    existing_files = {(a["category"], a["filename"]) for a in data["articles"]}

    new_found = []
    for cat_dir, cat_id in sorted(CATEGORY_MAP.items()):
        dir_path = os.path.join(PDF_DIR, cat_dir)
        if not os.path.isdir(dir_path):
            continue
        for f in sorted(os.listdir(dir_path)):
            if f.lower().endswith('.pdf') and (cat_id, f) not in existing_files:
                new_found.append((cat_dir, cat_id, f))

    if not new_found:
        print("No new PDFs found. Database is up to date.")
        return

    print(f"\nFound {len(new_found)} new PDF(s):\n")
    for i, (cat_dir, cat_id, filename) in enumerate(new_found, 1):
        print(f"  {i}. [{cat_dir}] {filename}")

    print(f"\nAdd all to database? (y/n): ", end="")
    ans = input().strip().lower()
    if ans != 'y':
        print("Cancelled.")
        return

    added = 0
    for cat_dir, cat_id, filename in new_found:
        filepath = os.path.join(PDF_DIR, cat_dir, filename)
        print(f"\nProcessing: {filename}...")

        text, page_count = extract_text(filepath)
        if not text:
            print(f"  SKIPPED (no text, image-only PDF)")
            continue

        title = extract_title(filename)
        keywords = extract_keywords(text, title)
        article_id = next_article_id(data)

        data["articles"].append({
            "id": article_id,
            "title": title,
            "filename": filename,
            "category": cat_id,
            "text": text,
            "pages": page_count,
            "keywords": keywords,
            "related": [],
        })
        print(f"  ADDED: {title} ({article_id}, {page_count}p, {len(text)} chars)")
        added += 1

    if added > 0:
        save_data(data)
        print(f"\nDone! Added {added} new article(s).")
    else:
        print("\nNo articles were added.")


def cmd_list(args):
    """List all articles in the database."""
    data = load_data()
    print(f"\n=== Pocket PPu Database ({data['total_articles']} articles) ===\n")

    for cat in data["categories"]:
        articles = [a for a in data["articles"] if a["category"] == cat["id"]]
        if not articles:
            continue
        print(f"[{cat['name_zh']}] ({cat['name_en']}) — {len(articles)} articles")
        for a in articles:
            print(f"  {a['id']}  {a['title']}  ({a['pages']}p, {len(a['text']):,} chars)")
        print()


def cmd_remove(args):
    """Remove an article by ID."""
    data = load_data()
    article_id = args.remove

    article = next((a for a in data["articles"] if a["id"] == article_id), None)
    if not article:
        print(f"ERROR: Article not found: {article_id}")
        print(f"Use --list to see all article IDs.")
        sys.exit(1)

    print(f"\nRemove: {article['title']} ({article_id})?")
    print(f"  Category: {article['category']}")
    print(f"  Pages: {article['pages']}")
    ans = input("Confirm? (y/n): ").strip().lower()
    if ans != 'y':
        print("Cancelled.")
        return

    data["articles"] = [a for a in data["articles"] if a["id"] != article_id]
    save_data(data)
    print(f"Removed: {article['title']}")


def cmd_rebuild(args):
    """Rebuild entire database from PDF folders."""
    print("WARNING: This will rebuild the entire database from scratch.")
    print("Any manually added text (image-only PDFs) will be LOST.")
    ans = input("Continue? (y/n): ").strip().lower()
    if ans != 'y':
        print("Cancelled.")
        return

    # Run the original extract script
    extract_script = "/Users/chengyangdata/tmua_health_download/extract_text.py"
    if os.path.exists(extract_script):
        pymupdf = get_pymupdf()
        if pymupdf:
            os.system(f"/tmp/pdfenv/bin/python3 {extract_script}")
            # Copy updated data
            src = "/Users/chengyangdata/tmua_health_download/pocket_ppu_data.json"
            if os.path.exists(src):
                shutil.copy2(src, DATA_FILE)
                print("Database rebuilt and copied.")
            # Re-run patch
            patch_script = "/Users/chengyangdata/tmua_health_download/patch_json.py"
            if os.path.exists(patch_script):
                os.system(f"/tmp/pdfenv/bin/python3 {patch_script}")
    else:
        print(f"ERROR: Extract script not found: {extract_script}")


# --- Main ---
def main():
    parser = argparse.ArgumentParser(
        description="Pocket PPu Update Tool — Manage health education articles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--add", metavar="PDF_PATH", help="Add a new PDF to the database")
    parser.add_argument("--category", metavar="CAT", help="Category folder name (required with --add)")
    parser.add_argument("--scan", action="store_true", help="Scan for new PDFs in all folders")
    parser.add_argument("--list", action="store_true", help="List all articles")
    parser.add_argument("--remove", metavar="ID", help="Remove an article by ID")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild entire database from PDFs")

    args = parser.parse_args()

    if args.add:
        if not args.category:
            print("ERROR: --category is required with --add")
            print("Example: python3 update_tool.py --add 'new.pdf' --category '01_攝護腺癌'")
            sys.exit(1)
        cmd_add(args)
    elif args.scan:
        cmd_scan(args)
    elif args.list:
        cmd_list(args)
    elif args.remove:
        cmd_remove(args)
    elif args.rebuild:
        cmd_rebuild(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
