#!/usr/bin/env python3
"""Extract PPu Teaching Notes from Clinical Note Generator HTML into structured JSON."""

import re
import json

HTML_FILE = "/Users/chengyangdata/Desktop/文件/URO Admission note/app/URO_Admission_Note.html"
OUTPUT = "/Users/chengyangdata/pocket-ppu/teaching-notes.json"

def extract():
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Extract the teaching notes modal content
    match = re.search(r'<h2>PPu Teaching Notes</h2>\s*<div[^>]*>(.*?)</div>\s*<div class="modal-btns">', html, re.DOTALL)
    if not match:
        print("ERROR: Could not find Teaching Notes section")
        return

    content = match.group(1)

    # Split by h3 headers (section boundaries)
    sections = []
    h3_pattern = r'<h3[^>]*>(.*?)</h3>'
    h3_matches = list(re.finditer(h3_pattern, content))

    for i, h3 in enumerate(h3_matches):
        title = re.sub(r'<[^>]+>', '', h3.group(1)).strip()
        start = h3.end()
        end = h3_matches[i + 1].start() if i + 1 < len(h3_matches) else len(content)
        section_html = content[start:end].strip()

        # Remove trailing <hr>
        section_html = re.sub(r'<hr[^>]*>\s*$', '', section_html).strip()

        # Parse subsections (h4) and items (li)
        subsections = []
        current_sub = None

        for line in section_html.split('\n'):
            line = line.strip()
            if not line:
                continue

            h4_match = re.search(r'<h4[^>]*>(.*?)</h4>', line)
            li_match = re.search(r'<li[^>]*>(.*?)</li>', line)
            p_match = re.search(r'<p[^>]*>(.*?)</p>', line)
            table_match = re.search(r'(<table.*?</table>)', line, re.DOTALL)

            if h4_match:
                sub_title = re.sub(r'<[^>]+>', '', h4_match.group(1)).strip()
                current_sub = {"title": sub_title, "items": []}
                subsections.append(current_sub)
            elif li_match:
                item_text = li_match.group(1).strip()
                # Keep <strong> tags as **text** for markdown
                item_text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', item_text)
                item_text = re.sub(r'<[^>]+>', '', item_text)
                if current_sub:
                    current_sub["items"].append(item_text)
                else:
                    current_sub = {"title": "", "items": [item_text]}
                    subsections.append(current_sub)
            elif p_match:
                p_text = p_match.group(1).strip()
                p_text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', p_text)
                p_text = re.sub(r'<[^>]+>', '', p_text)
                if current_sub:
                    current_sub["items"].append(p_text)
                else:
                    current_sub = {"title": "", "items": [p_text]}
                    subsections.append(current_sub)
            elif table_match:
                # Convert table to text representation
                table_html = table_match.group(1)
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
                table_lines = []
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                    table_lines.append(" | ".join(cells))
                table_text = "\n".join(table_lines)
                if current_sub:
                    current_sub["items"].append(table_text)
                else:
                    current_sub = {"title": "", "items": [table_text]}
                    subsections.append(current_sub)

        # Extract section number from title
        num_match = re.match(r'([\u4e00-\u9fff\d]+)[\u3001、．.](.+)', title)
        if num_match:
            section_num = num_match.group(1)
            section_title = num_match.group(2).strip()
        else:
            section_num = str(i + 1)
            section_title = title

        sections.append({
            "id": f"tn_{i:02d}",
            "number": section_num,
            "title": section_title,
            "full_title": title,
            "subsections": subsections,
        })

        print(f"  [{section_num}] {section_title} ({len(subsections)} subsections)")

    # Build output
    output = {
        "version": "1.0.0",
        "updated": "2026-03-27",
        "author": "PPu Teaching Faculty",
        "total_sections": len(sections),
        "sections": sections,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nExtracted {len(sections)} sections to {OUTPUT}")
    print(f"Size: {len(json.dumps(output, ensure_ascii=False)) / 1024:.1f} KB")


if __name__ == "__main__":
    extract()
