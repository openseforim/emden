"""Build the GitHub Pages reader in docs/.
  py -3.13 scripts/build_site.py
Inputs:
  translation/*.md          sections '## Page N (scan M)' or '## Typed insert ... (scan M) ...'
  data/text/sMMM.he.txt     checked Hebrew, + sMMM.notes.txt (Kahana's notes)
  data/scholem/notes_*.tsv  margin readings in Scholem's copy (V = omission, X = substitution)
  data/site/intro.md        introduction for general readers (home page)
  data/site/entities.json   index of people, places, books (regex patterns over the English)
  data/site/review.json     review status per page (default: draft)
  scripts/site/*            style.css, app.js, search.js (copied as they are)
  kahana_1896_hb37017.pdf   the scan (only to render docs/scans/sMMM.png when missing)
Output: docs/index.html, docs/chN.html, docs/names.html, docs/search.html, docs/search.json, docs/scans/."""
import csv
import html
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import markdown

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = ROOT / "data" / "site"
ASSETS = Path(__file__).resolve().parent / "site"
PDF = ROOT / "kahana_1896_hb37017.pdf"
REPO = "https://github.com/openseforim/emden"
HB = "https://hebrewbooks.org/pdfpager.aspx?req=37017&pgnum={}"
SEC = re.compile(r"^## (.+?)\s*$", re.M)

# Chapters by scan range. A chapter that begins in the middle of a page is filed with the chapter that page
# starts in; the break itself is marked in the text ("[*Here chapter N begins ...*]").
CHAPTERS = [
    {"n": 1, "sub": "Emden's ancestors and the life of his father, Ḥakham Tzvi", "first": 11, "last": 66, "starts": "p. 3"},
    {"n": 2, "sub": "Emden's own life, from his youth", "first": 67, "last": 115, "starts": "p. 54"},
    {"n": 3, "sub": "From Amsterdam to Emden, and the rabbinate there", "first": 116, "last": 130, "starts": "p. 99"},
    {"n": 4, "sub": "Settling in Altona", "first": 131, "last": 170, "starts": "p. 114"},
    {"n": 5, "sub": "Life in Altona, continued", "first": 171, "last": 187, "starts": "p. 150"},
    {"n": 6, "sub": "The printing press", "first": 188, "last": 197, "starts": "p. 167"},
    {"n": 7, "sub": "Flight to Amsterdam, 1751", "first": 198, "last": 211, "starts": "p. 177"},
    {"n": 8, "sub": "The houses in Altona; the end of Emden's text, and Kahana's continuation to his death", "first": 212, "last": 240, "starts": "p. 189"},
    {"n": 9, "label": "Appendix", "sub": "Kahana's addition (the damaged opening leaves) and his list of omissions", "first": 241, "last": 9999, "starts": "p. 217"},
]

BOOKS = {
    "Gen": "Genesis", "Ex": "Exodus", "Exod": "Exodus", "Lev": "Leviticus", "Num": "Numbers", "Deut": "Deuteronomy",
    "Josh": "Joshua", "Judg": "Judges", "1 Sam": "I_Samuel", "2 Sam": "II_Samuel", "1 Kgs": "I_Kings",
    "2 Kgs": "II_Kings", "Isa": "Isaiah", "Jer": "Jeremiah", "Ezek": "Ezekiel", "Hos": "Hosea", "Joel": "Joel",
    "Amos": "Amos", "Obad": "Obadiah", "Jon": "Jonah", "Jonah": "Jonah", "Mic": "Micah", "Nah": "Nahum",
    "Hab": "Habakkuk", "Zeph": "Zephaniah", "Hag": "Haggai", "Zech": "Zechariah", "Mal": "Malachi",
    "Ps": "Psalms", "Prov": "Proverbs", "Job": "Job", "Song": "Song_of_Songs", "Ruth": "Ruth",
    "Lam": "Lamentations", "Eccl": "Ecclesiastes", "Esth": "Esther", "Dan": "Daniel", "Ezra": "Ezra",
    "Neh": "Nehemiah", "1 Chr": "I_Chronicles", "2 Chr": "II_Chronicles", "Avot": "Pirkei_Avot",
}
BIBLE = re.compile(r"\b(" + "|".join(sorted((re.escape(k) for k in BOOKS), key=len, reverse=True))
                   + r")\.? (\d+):(\d+)(?:[–-](\d+))?(?![\d:])")
TALMUD = re.compile(r"\bb\. ((?:[A-Z][\w'ḥḤ]*)(?: [A-Z][\w'ḥḤ]*)?) (\d+[ab])\b")
TRACTATE_FIX = {"Ketubbot": "Ketubot"}


def sefaria_tractate(name):
    name = TRACTATE_FIX.get(name, name)
    return name.replace("Ḥ", "Ch").replace("ḥ", "ch").replace("'", "").replace(" ", "_")


# ---------------------------------------------------------------- inputs

def sections():
    out = {}
    for f in sorted((ROOT / "translation").glob("*.md")):
        t = f.read_text(encoding="utf-8")
        parts = SEC.split(t)
        for title, body in zip(parts[1::2], parts[2::2]):
            m = re.search(r"\(scan (\d+)\)", title)
            if not m:
                continue
            body = body.strip().rstrip("-").strip()
            eng, _, notes = body.partition("**Kahana's notes**")
            out[int(m.group(1))] = {"title": title, "en": eng.strip(), "kahana_en": notes.strip()}
    return out


def scholem():
    rows = {}
    for f in sorted((ROOT / "data" / "scholem").glob("notes_*.tsv")):
        with f.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                rows.setdefault(int(r["scan_page"]), []).append(r)
    return rows


def hebrew_plain(scan):
    p = ROOT / "data" / "text" / f"s{scan:03d}.he.txt"
    if not p.exists():
        return ""
    lines = [l.rstrip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines = [l for l in lines if not (l.startswith("[TYPED INSERT") or l.startswith("[HANDWRITTEN SHEET"))]
    text = ""
    for l in lines:
        if text.endswith("-"):
            text = text[:-1] + l
        else:
            text += (" " if text else "") + l
    return text


def hebrew(scan):
    return re.sub(r"\[([א-ט])\]", r'<sup class="fn">\1</sup>', html.escape(hebrew_plain(scan)))


def hebrew_notes_list(scan):
    p = ROOT / "data" / "text" / f"s{scan:03d}.notes.txt"
    if not p.exists():
        return []
    t = p.read_text(encoding="utf-8").strip()
    if not t:
        return []
    notes, cur = [], ""
    for l in t.splitlines():
        if re.match(r"^\[[א-ט]\]", l) and cur:
            notes.append(cur)
            cur = l
        else:
            cur = (cur + " " + l).strip()
    notes.append(cur)
    return [n for n in notes if n]


# ---------------------------------------------------------------- linking

class Linker:
    """Links Bible/Talmud references to Sefaria and index names to names.html, in rendered HTML text only."""

    def __init__(self, entities):
        self.entities = entities
        parts = []
        for i, e in enumerate(entities):
            for p in e["patterns"]:
                parts.append((len(p), i, p))
        parts.sort(reverse=True)
        self.group_ent = {}
        alts = []
        for k, (_, i, p) in enumerate(parts):
            self.group_ent[f"g{k}"] = i
            alts.append(f"(?P<g{k}>\\b(?:{p})(?!\\w))")
        self.rx = re.compile("|".join(alts))
        self.hits = {e["id"]: [] for e in entities}

    def _refs(self, text):
        def bib(m):
            book, ch, v1, v2 = m.groups()
            ref = f"{BOOKS[book]}.{ch}.{v1}" + (f"-{v2}" if v2 else "")
            return f'<a class="ref" href="https://www.sefaria.org/{ref}?lang=bi" target="_blank" rel="noopener">{m.group(0)}</a>'

        def tal(m):
            ref = f"{sefaria_tractate(m.group(1))}.{m.group(2)}"
            return f'<a class="ref" href="https://www.sefaria.org/{ref}?lang=bi" target="_blank" rel="noopener">{m.group(0)}</a>'

        return TALMUD.sub(tal, BIBLE.sub(bib, text))

    def link(self, rendered, page_ref):
        seen = set()
        out, in_a = [], 0
        for tok in re.split(r"(<[^>]+>)", rendered):
            if tok.startswith("<"):
                if re.match(r"<a\b", tok):
                    in_a += 1
                elif tok.startswith("</a"):
                    in_a = max(0, in_a - 1)
                out.append(tok)
                continue
            if in_a or not tok:
                out.append(tok)
                continue

            def ent(m):
                e = self.entities[self.group_ent[m.lastgroup]]
                self.hits[e["id"]].append(page_ref)
                if e["id"] in seen:
                    return m.group(0)
                seen.add(e["id"])
                return f'<a class="nm" href="names.html#{e["id"]}" title="{html.escape(e["name"])}">{m.group(0)}</a>'

            # names first (on plain text), then references on the text between the new links
            pieces = re.split(r"(<a [^>]+>.*?</a>)", self.rx.sub(ent, tok))
            out.append("".join(p if p.startswith("<a ") else self._refs(p) for p in pieces))
        return "".join(out)


def mark_kind(row):
    """V = omission (caret), X = substitution, per the key sheet in the copy; '' if not recorded."""
    m = row["mark"].lower()
    if "x mark" in m:
        return "X"
    if "caret" in m or "v mark" in m:
        return "V"
    return ""


def align_marks(n_inline, rows):
    """Match the inline ⟨S: …⟩ readings of a page to its TSV rows, in order. Rows without a margin reading
    (bracket marks only, pointers to an inserted sheet) have no inline reading; drop them if that makes the counts
    agree. Returns a list of rows (one per inline reading) or None if the match is not clear."""
    if n_inline == len(rows):
        return rows
    kept = [r for r in rows if r["margin_text_reading"].strip() not in ("-", "")
            and not r["margin_text_reading"].startswith("(see scan") and "sheet" not in r["anchor_in_print"]]
    return kept if n_inline == len(kept) else None


def sch_span(row):
    k = mark_kind(row) if row else ""
    anchor = html.escape(row["anchor_in_print"]) if row else ""
    if k == "X":
        t = f"X in the margin: by the key sheet, a substitution: the Oxford MS has these words instead of the printed ones (at: {anchor})"
    elif k == "V":
        t = f"V (caret) in the margin: by the key sheet, an omission: these words are missing in the print (at: {anchor})"
    else:
        t = "Margin reading from the Oxford MS (type of mark not recorded)"
    cls = {"X": " sch-x", "V": " sch-v"}.get(k, "")
    return f'<span class="sch{cls}" title="{t}">'


def md(s, marks=None):
    if marks is not None:
        s = re.sub("⟨S:", lambda m: sch_span(next(marks, None)) + "⟨\u0001S:", s)
    s = re.sub(r"^\[\*Here chapter (\d+) begins([^*]*)\*\]\s*$",
               lambda m: f'\n<div class="chapbreak" id="chapter-{m.group(1)}"><span>Chapter {m.group(1)} begins here</span>'
                         f'<small>{html.escape(m.group(2).strip().rstrip("."))}</small></div>\n',
               s, flags=re.M)
    s = re.sub(r"\*\*\[([a-z])\]\*\*", r'<strong class="fn-en">[\1]</strong>', s)
    s = s.replace("⟨S:", '<span class="sch">⟨S:').replace("\u0001", "").replace("⟩", "⟩</span>")
    return markdown.markdown(s, extensions=["extra"])


def plain_md(s):
    s = re.sub(r"[*_`#]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- page parts

def head(title, desc, extra=""):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="website">
<script>(function(){{try{{var t=localStorage.getItem('os-theme');if(t&&t!=='auto')document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif:ital,wght@0,400;0,600;1,400&family=Noto+Serif+Hebrew:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">{extra}
<link rel="stylesheet" href="/assets/os.css">
<script src="/assets/os.js" defer></script>
</head>"""


def bar(chapters, current, reader=False):
    links = [f'<a href="index.html"{" aria-current=page" if current == "home" else ""}>Introduction</a>']
    for c in chapters:
        if c["secs"]:
            cur = " aria-current=page" if current == c["n"] else ""
            links.append(f'<a href="ch{c["n"]}.html"{cur}>{c.get("label", "Ch. %d" % c["n"])}</a>')
    links.append(f'<a href="background.html"{" aria-current=page" if current == "background" else ""}>Background</a>')
    links.append(f'<a href="names.html"{" aria-current=page" if current == "names" else ""}>Index</a>')
    controls = ""
    if reader:
        controls = """
  <div class="ctl">
    <span class="seg" role="group" aria-label="Languages">
      <button type="button" data-view="both">Both</button><button type="button" data-view="he">Hebrew</button><button type="button" data-view="en">English</button>
    </span>
    <label><input type="checkbox" id="opt-notes" checked> Kahana's notes</label>
    <label><input type="checkbox" id="opt-scan"> Scan</label>
  </div>"""
    return f"""<div class="bar"><div class="wrap barin">
  <a class="brand" href="index.html">Megillat Sefer</a>
  <nav class="nav">{' '.join(links)}</nav>{controls}
  <form class="sform" action="search.html" role="search"><input type="search" name="q" placeholder="Search Hebrew or English" aria-label="Search"></form>
  <select id="theme" aria-label="Theme"><option value="auto">Auto</option><option value="light">Light</option><option value="paper">Paper</option><option value="dark">Dark</option></select>
</div></div>"""


def foot():
    return f"""<footer class="wrap foot">Draft translation by Claude (Anthropic), not yet reviewed. Hebrew: Kahana, Warsaw 1896/97 (public domain).
Translation and notes CC BY-SA 4.0. <a href="{REPO}">Source on GitHub</a> · <a href="{REPO}/issues">corrections and questions</a>.</footer>
<script src="app.js"></script>
</body></html>"""


def page_label(s):
    m = re.match(r"Page (\d+)", s["title"])
    return (f"p. {m.group(1)}", f"p{m.group(1)}") if m else ("insert", f"s{s['scan']}")


def cname(c):
    return c.get("label", f"Chapter {c['n']}")


def start_link(c, chapters, link_file):
    """The page where a chapter begins; if it begins inside the previous chapter's last page, link the break."""
    prev = next((p for p in chapters if p["n"] == c["n"] - 1 and p["secs"]), None)
    if prev and c["secs"] and prev["secs"][-1]["label"] == c["starts"]:
        return f'<a href="ch{prev['n']}.html#chapter-{c['n']}">{c["starts"]}</a>'
    return c["starts"]


def toc_html(chapters, link_file=True, only=None):
    out = []
    for c in chapters:
        if only is not None and c["n"] != only:
            continue
        if c["secs"]:
            links = " · ".join(f'<a href="{"ch%d.html" % c["n"] if link_file else ""}#{s["anchor"]}">{s["label"]}</a>' for s in c["secs"])
            first, last = c["secs"][0]["label"], c["secs"][-1]["label"]
            out.append(f'<div class="tocch"><h3><a href="ch{c["n"]}.html">{cname(c)}</a> <span>{html.escape(c["sub"])} · from {start_link(c, chapters, link_file)}</span></h3>'
                       f'<p class="toc">{links}</p></div>')
        else:
            prev = next((p for p in chapters if p["n"] == c["n"] - 1), None)
            href = f'ch{prev["n"]}.html#chapter-{c["n"]}' if prev and prev["secs"] else "#"
            out.append(f'<div class="tocch"><h3><a href="{href}">{cname(c)}</a> <span>begins on {c["starts"]}; {html.escape(c["sub"])}</span></h3></div>')
    return "\n".join(out)


def render_scans(scans):
    out = DOCS / "scans"
    out.mkdir(exist_ok=True)
    todo = [s for s in scans if not (out / f"s{s:03d}.png").exists()]
    if not todo:
        return
    if not PDF.exists():
        print(f"WARNING: {PDF.name} missing; {len(todo)} scan images not rendered")
        return
    import pymupdf
    from PIL import Image
    doc = pymupdf.open(PDF)
    for i, s in enumerate(todo, 1):
        pix = doc[s - 1].get_pixmap(dpi=250, colorspace=pymupdf.csGRAY)
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples).convert("1")
        im.save(out / f"s{s:03d}.png", optimize=True)
        if i % 20 == 0:
            print(f"scans {i}/{len(todo)}", flush=True)
    print(f"rendered {len(todo)} scan images")


# ---------------------------------------------------------------- main

def main():
    DOCS.mkdir(exist_ok=True)
    secs, sch = sections(), scholem()
    entities = [e for e in json.loads((SITE / "entities.json").read_text(encoding="utf-8")) if e.get("patterns")]
    review = json.loads((SITE / "review.json").read_text(encoding="utf-8"))
    linker = Linker(entities)

    chapters = [dict(c, secs=[]) for c in CHAPTERS]
    last = "?"
    for scan in sorted(secs):
        s = secs[scan]
        s["scan"] = scan
        s["label"], s["anchor"] = page_label(s)
        if s["label"] == "insert":
            s["long"] = f"insert after p. {last}"
        else:
            s["long"] = s["label"]
            last = s["label"][3:]
        c = next(c for c in chapters if c["first"] <= scan <= c["last"])
        s["ch"] = c["n"]
        c["secs"].append(s)

    search, unmatched = [], []
    for c in chapters:
        if not c["secs"]:
            continue
        fname = f"ch{c['n']}.html"
        body = []
        for s in c["secs"]:
            scan, anchor = s["scan"], s["anchor"]
            ref = (fname, anchor, s["long"])
            sn = sch.get(scan, [])
            sch_html = ""
            if sn:
                kind_txt = {"X": "X: substitution", "V": "V: omission", "": "—"}
                sch_html = "<details class='schbox'><summary>Margin readings in Scholem's copy ({})</summary><table><tr><th>Printed anchor</th><th>Type (key sheet)</th><th>Mark</th><th>Reading</th><th>Certainty</th></tr>{}</table></details>".format(
                    len(sn), "".join(f"<tr><td dir='rtl'>{html.escape(r['anchor_in_print'])}</td><td>{kind_txt[mark_kind(r)]}</td><td>{html.escape(r['mark'])}</td>"
                                     f"<td dir='rtl'>{html.escape(r['margin_text_reading'])}</td><td>{html.escape(r['certainty'])}</td></tr>" for r in sn))
            n_inline = (s["en"] + s["kahana_en"]).count("⟨S:")
            matched = align_marks(n_inline, sn) if n_inline else []
            if n_inline and matched is None:
                unmatched.append(s["long"])
            marks = iter(matched or [])
            he_notes = hebrew_notes_list(scan)
            he_notes_html = "".join(f"<li>{html.escape(n)}</li>" for n in he_notes)
            en_html = linker.link(md(s["en"], marks), ref)
            kn_html = ""
            if s["kahana_en"]:
                kn_html = '<div class="knotes-en"><h3>Kahana\'s notes</h3>' + linker.link(md(s["kahana_en"], marks), ref) + "</div>"
            status = review.get("pages", {}).get(anchor, review.get("default", "draft"))
            badge = review.get("labels", {}).get(status, status)
            body.append(f"""
<section class="page" id="{anchor}" data-label="{s['long']}" data-ch="{c['n']}">
  <header><h2><a class="self" href="#{anchor}">{html.escape(s['title'])}</a></h2>
  <span class="meta"><span class="badge {status}">{html.escape(badge)}</span>
  <a class="fix" href="{REPO}/issues/new" target="_blank" rel="noopener">Suggest a correction</a>
  <a class="scanlink" href="{HB.format(scan)}" target="_blank" rel="noopener">HebrewBooks scan {scan} ↗</a></span></header>
  <div class="cols">
    <div class="en" lang="en">{en_html}{kn_html}</div>
    <div class="he" dir="rtl" lang="he">{('<p>' + hebrew(scan) + '</p>') if hebrew_plain(scan) else '<p class="pending" dir="ltr">The checked Hebrew of this page is not ready yet (OCR pending). See the scan.</p>'}{f'<ol class="knotes">{he_notes_html}</ol>' if he_notes_html else ''}</div>
    <figure class="scanimg"><img data-src="scans/s{scan:03d}.png" alt="Scan page {scan} (Scholem's copy of Kahana's edition)" width="1094" height="1719" loading="lazy"><figcaption>Scan {scan}</figcaption></figure>
  </div>
  {sch_html}
</section>""")
            search.append({"f": fname, "a": anchor, "l": s["long"], "c": c["n"],
                           "h": hebrew_plain(scan) + " " + " ".join(he_notes),
                           "e": plain_md(s["en"] + " " + s["kahana_en"]).replace("⟨S:", "⟨MS margin:")})
        n = c["n"]
        prevc = next((p for p in chapters if p["n"] == n - 1 and p["secs"]), None)
        nextc = next((p for p in chapters if p["n"] == n + 1 and p["secs"]), None)
        pn = " · ".join(x for x in [
            f'<a href="ch{prevc["n"]}.html">← {cname(prevc)}</a>' if prevc else "",
            f'<a href="ch{nextc["n"]}.html">{cname(nextc)} →</a>' if nextc else ""] if x)
        title = f"Megillat Sefer, {cname(c).lower()}"
        page = (head(title, f"Jacob Emden's autobiography, {cname(c).lower()}: {c['sub']}. Hebrew (Kahana 1896/97) with English draft translation.")
                + f'<body class="reader">{bar(chapters, n, reader=True)}<div class="wrap">'
                + f'<div class="top"><h1>{cname(c)} <span class="sub">{html.escape(c["sub"])}</span></h1>'
                + f'<p class="sub">Jacob Emden, <i>Megillat Sefer</i> · Hebrew (Kahana, Warsaw 1896/97) with an English draft translation · work in progress</p>'
                + f'<details class="pages" open><summary>Pages in this chapter</summary>{toc_html(chapters, link_file=False, only=n)}</details></div>'
                + "\n".join(body)
                + f'<p class="pn">{pn}</p></div>' + foot())
        (DOCS / fname).write_text(page, encoding="utf-8")
        print(f"docs/{fname}: {len(c['secs'])} sections")

    # home page
    intro = markdown.markdown((SITE / "intro.md").read_text(encoding="utf-8"), extensions=["extra"])
    home = (head("Jacob Emden, Megillat Sefer: Hebrew and English",
                 "Reader for Jacob Emden's autobiography Megillat Sefer: Kahana's Hebrew text (1896/97) from Gershom Scholem's annotated copy, with an English draft translation.")
            + f'<body>{bar(chapters, "home")}<div class="wrap">'
            + '<div class="top"><h1>Jacob Emden, <i>Megillat Sefer</i></h1>'
            + '<p class="sub">Hebrew (Kahana, Warsaw 1896/97, from Gershom Scholem\'s copy) with an English draft translation · work in progress</p></div>'
            + f'<div class="home"><article class="intro">{intro}</article>'
            + f'<aside class="contents"><h2>Contents</h2>{toc_html(chapters)}<p class="sub"><a href="names.html">Index of names, places and books</a></p></aside></div>'
            + ABOUT + "</div>"
            # old links (index.html#p12) went to the single-page reader: send them to the chapter page
            + "<script>(function(){var m=" + json.dumps({s["anchor"]: f"ch{c['n']}.html" for c in chapters for s in c["secs"]})
            + ";var h=location.hash.slice(1);if(m[h])location.replace(m[h]+'#'+h);})();</script>"
            + foot())
    (DOCS / "index.html").write_text(home, encoding="utf-8")

    # index of names
    labels = {"person": "People", "place": "Places", "work": "Books", "scholar": "Modern scholars and editors"}

    def sortkey(e):
        return unicodedata.normalize("NFD", e["name"]).encode("ascii", "ignore").decode().lower().lstrip("(")

    groups = []
    for t, lab in labels.items():
        items = []
        for e in sorted((e for e in entities if e["type"] == t), key=sortkey):
            hits = linker.hits[e["id"]]
            if not hits:
                continue
            seen, links = set(), []
            for f, a, l in hits:
                if (f, a) in seen:
                    continue
                seen.add((f, a))
                links.append(f'<a href="{f}#{a}">{l}</a>')
            desc = f' <span class="desc">{html.escape(e["desc"])}</span>' if e.get("desc") else ""
            items.append(f'<li id="{e["id"]}"><b>{html.escape(e["name"])}</b>{desc}<div class="hits">{" · ".join(links)}</div></li>')
        groups.append(f'<h2>{lab} <span class="sub">({len(items)})</span></h2><ul class="idx">{"".join(items)}</ul>')
    jump = " · ".join(f'<a href="#t-{t}">{lab}</a>' for t, lab in labels.items())
    names = (head("Megillat Sefer: index of names", "Index of people, places and books in the English draft translation of Jacob Emden's Megillat Sefer.")
             + f'<body>{bar(chapters, "names")}<div class="wrap"><div class="top"><h1>Index</h1>'
             + '<p class="sub">People, places and books named in the English draft (main text and Kahana\'s notes). Built by name patterns, so '
             + 'mentions by title only ("my father", "the gaon") are not listed. Each page link goes to the page where the name occurs.</p>'
             + f'<p class="toc">{jump}</p></div>'
             + "".join(g.replace("<h2>", f'<h2 id="t-{t}">', 1) for g, t in zip(groups, labels)) + "</div>" + foot())
    (DOCS / "names.html").write_text(names, encoding="utf-8")

    # background for general readers (BACKGROUND.md at the repo root)
    bg_md = (ROOT / "BACKGROUND.md").read_text(encoding="utf-8")
    bg_md = re.sub(r"^# .*\n", "", bg_md, count=1)
    bg = (head("Megillat Sefer: background for the reader",
               "Historical, medical and everyday background for reading Jacob Emden's autobiography Megillat Sefer.")
          + f'<body>{bar(chapters, "background")}<div class="wrap"><div class="top"><h1>Background for the reader</h1></div>'
          + f'<article class="intro bgnote">{markdown.markdown(bg_md, extensions=["extra"])}</article></div>' + foot())
    (DOCS / "background.html").write_text(bg, encoding="utf-8")

    # search
    (DOCS / "search.json").write_text(json.dumps(search, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    srch = (head("Megillat Sefer: search", "Search the Hebrew text and English draft translation of Jacob Emden's Megillat Sefer.")
            + f'<body>{bar(chapters, "search")}<div class="wrap"><div class="top"><h1>Search</h1>'
            + '<p class="sub">Searches the Hebrew (with Kahana\'s notes) and the English. Hebrew search ignores gershayim and quotation marks; '
            + 'English search ignores accents (Hakham finds Ḥakham).</p>'
            + '<form id="sf" class="bigsearch"><input type="search" id="q" name="q" autofocus aria-label="Search"> '
            + '<select id="lang" aria-label="Language"><option value="all">Hebrew and English</option><option value="he">Hebrew</option><option value="en">English</option></select></form>'
            + '<p id="status" class="sub"></p></div><ol id="results" class="results"></ol></div>'
            + '<script src="search.js"></script>' + foot())
    (DOCS / "search.html").write_text(srch, encoding="utf-8")

    for f in ASSETS.iterdir():
        shutil.copy(f, DOCS / f.name)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    render_scans(sorted(secs))
    used = sum(1 for e in entities if linker.hits[e["id"]])
    print(f"index: {used}/{len(entities)} entities with hits; search: {len(search)} sections")
    if unmatched:
        print("margin readings not matched to TSV rows (shown without X/V type):", ", ".join(unmatched))


ABOUT = """
<details class="about"><summary>Sources and method</summary>
<p><b>Hebrew:</b> David Kahana's edition (Warsaw 1896/97), from the HebrewBooks scan no. 37017, which is Gershom
Scholem's copy (his library stamp is on scan p. 196). OCR by Kraken with the PP-OCRv6 model, then checked line by line
against the scan by Claude. Running heads and page numbers are removed; Kahana's footnote calls are shown as small
letters. The Pninim text of Bick's edition (Jerusalem 1979) was used only to find OCR errors.</p>
<p><b>English:</b> draft translation by Claude (Anthropic), not yet reviewed. Biblical phrases are given in standard
wording with the reference. Kahana's own footnotes are translated under each page.</p>
<p><b>Margin readings in Scholem's copy:</b> by a handwritten key sheet in the copy (seen in the National Library of
Israel's scan, IE12757688; not in the HebrewBooks scan), they follow the Oxford manuscript, V marks an omission and X a
substitution, and the copy was compared with the manuscript by Ḥayyim Wirszubski. Our reading of the sheet is not
certain in every word. The readings are shown as <span class="sch sch-v">⟨S: …⟩</span> (V, addition) or
<span class="sch sch-x">⟨S: …⟩</span> (X, substitution) where their mark points, and listed with their certainty
under each page; hover over a reading to see the printed words it belongs to. Where the type is not recorded the plain
style <span class="sch">⟨S: …⟩</span> is used. Typed sheets bound into the copy (after pp. 8, 40 and 70) and a
handwritten sheet (after p. 58) are given as "insert" sections. The HebrewBooks scan cuts off part of the right
margin; the NLI scan of the same copy (258 images) shows the full margins and has not yet been used.</p>
<p><b>Not the manuscript:</b> Kahana's text is not a full transcription of the Oxford manuscript (Bodleian, MS. Mich. 587; Neubauer
1723). A critical edition by Jacob J. Schacter has been announced.</p>
</details>"""

if __name__ == "__main__":
    main()
