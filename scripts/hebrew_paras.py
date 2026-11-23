"""Paragraph breaks of the printed Hebrew (Kahana 1896), from Kraken line segmentation of the page images.

The checked Hebrew (data/text/sNNN.he.txt) has one text line per printed line, but no paragraph marks. The edition
starts a paragraph with an indented line and ends one with a short line. Kraken finds the printed lines; their ends
show the indents and the short lines.

  py -3.13 scripts/hebrew_paras.py segment [WORKERS]     Kraken baselines -> data/kseg/sNNN.json (resumable)
  py -3.13 scripts/hebrew_paras.py breaks [SCAN ...]     -> data/hebrew_paras.json, and a report

data/hebrew_paras.json: {"sNNN": {"starts": [line numbers, 1-based, that begin a paragraph], "why": {...},
"lines": n, "column_lines": n, "last_short": bool}}. A page whose column line count differs from its text
line count gets no breaks ("mismatch": true) and is listed in the report."""
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
KRAKEN = Path(r"C:\Users\ezrab\Ezra Brandt\Claude\syriac-ocr\.venv\Scripts\kraken.exe")
RAW, KSEG, TEXT = ROOT / "data" / "raw", ROOT / "data" / "kseg", ROOT / "data" / "text"
OUT = ROOT / "data" / "hebrew_paras.json"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def scans():
    return sorted(int(p.name[1:4]) for p in TEXT.glob("s*.he.txt"))


# ---------------------------------------------------------------- segment

def seg_one(n):
    out = KSEG / f"s{n:03d}.json"
    if out.exists():
        return f"s{n:03d} skip"
    img = RAW / f"s{n:03d}.png"
    if not img.exists():
        return f"s{n:03d} NO IMAGE"
    t = time.time()
    tmp = out.with_suffix(".tmp")
    r = subprocess.run([str(KRAKEN), "-i", str(img), str(tmp), "segment", "-bl"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    if r.returncode or not tmp.exists():
        return f"s{n:03d} FAILED: {r.stderr[-300:]}"
    tmp.replace(out)
    return f"s{n:03d} ok {time.time() - t:.0f}s"


def segment(workers):
    KSEG.mkdir(parents=True, exist_ok=True)
    pages = scans()
    with ThreadPoolExecutor(workers) as ex:
        for i, msg in enumerate(ex.map(seg_one, pages), 1):
            print(f"{i}/{len(pages)} {msg}", flush=True)
    print("finished", flush=True)


# ---------------------------------------------------------------- breaks

def he_lines(scan):
    return [l.rstrip() for l in (TEXT / f"s{scan:03d}.he.txt").read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith(("[TYPED INSERT", "[HANDWRITTEN SHEET"))]


def kraken_lines(scan):
    j = json.loads((KSEG / f"s{scan:03d}.json").read_text(encoding="utf-8"))
    out = []
    for ln in j.get("lines", []):
        bl = ln.get("baseline") or []
        if len(bl) >= 2:
            out.append({"x0": min(p[0] for p in bl), "x1": max(p[0] for p in bl), "y": statistics.mean(p[1] for p in bl)})
    return out


def main_column(lines, scan):
    """The printed lines of the text block, top to bottom. Kraken gives each line's height and ends; where Kraken
    merged a margin note into a printed line, the ends come from the ink in the image, cut at the text column."""
    import numpy as np
    from PIL import Image
    widths = sorted(l["x1"] - l["x0"] for l in lines)
    full = widths[int(len(widths) * 0.75)]
    longs = [l for l in lines if 0.85 * full < l["x1"] - l["x0"] < 1.08 * full]
    R = statistics.median(l["x1"] for l in longs)  # right margin: where a Hebrew line starts
    L = statistics.median(l["x0"] for l in longs)  # left margin: where a full line ends
    W = R - L
    cand = sorted((l for l in lines if min(l["x1"], R) - max(l["x0"], L) > 0.03 * W), key=lambda l: l["y"])
    fy = sorted(l["y"] for l in cand if min(l["x1"], R) - max(l["x0"], L) > 0.8 * W)
    steps = [b - a for a, b in zip(fy, fy[1:]) if b - a > 20]
    gap = statistics.median(steps) if len(steps) > 2 else 80  # line spacing, from full lines only
    ov = lambda z: min(z["x1"], R) - max(z["x0"], L)
    keep = []  # one Kraken line per printed line: the one that overlaps the column most
    for l in cand:
        if keep and l["y"] - keep[-1]["y"] < 0.4 * gap:
            if ov(l) > ov(keep[-1]):
                keep[-1] = l
            continue
        keep.append(l)
    a = np.asarray(Image.open(RAW / f"s{scan:03d}.png").convert("L")) < 110
    tol = 0.015 * W
    col = []
    for l in keep:
        x0, x1 = l["x0"], l["x1"]
        if x1 > R + tol or x0 < L - tol:
            band = a[max(0, int(l["y"] - 0.55 * gap)):int(l["y"] + 0.12 * gap), int(L):int(R) + 1]
            ink = np.where(band.sum(0) > 1)[0]
            if not len(ink):
                continue
            if x1 > R + tol:
                x1 = L + ink.max()
            if x0 < L - tol:
                x0 = L + ink.min()
        col.append({"y": l["y"], "x0": x0, "x1": x1})
    if len(col) > 2 and col[1]["y"] - col[0]["y"] > 1.6 * gap:  # running head
        col = col[1:]
    for i in range(1, len(col)):  # footnotes: after the first wide gap
        if col[i]["y"] - col[i - 1]["y"] > 1.6 * gap:
            col = col[:i]
            break
    return col, L, R


def page_breaks(scan):
    text = he_lines(scan)
    col, L, R = main_column(kraken_lines(scan), scan)
    W = R - L
    rec = {"lines": len(text), "column_lines": len(col), "starts": [], "why": {}}
    if len(col) != len(text):
        rec["mismatch"] = True
        return rec
    for i in range(1, len(col)):
        indent = R - col[i]["x1"]
        short_prev = col[i - 1]["x0"] - L
        why = []
        if indent > 0.025 * W:
            why.append(f"indent {indent / W:.0%}")
        if short_prev > 0.06 * W:
            why.append(f"prev short {short_prev / W:.0%}")
        if indent > 0.025 * W:  # a set-off block: same indent as the line before, which reached the block's edge
            p_indent, p_left = R - col[i - 1]["x1"], short_prev
            block_left = min(p_left, col[i]["x0"] - L)
            if i >= 2 and abs((R - col[i - 2]["x1"]) - p_indent) < 0.015 * W:
                block_left = min(block_left, col[i - 2]["x0"] - L)
            if abs(indent - p_indent) < 0.015 * W and p_left <= block_left + 0.04 * W:
                why = []
        if why:
            rec["starts"].append(i + 1)
            rec["why"][str(i + 1)] = ", ".join(why)
    rec["last_short"] = bool((col[-1]["x0"] - L) / W > 0.06) if col else False
    return rec


def breaks(only):
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    pages = only or [s for s in scans() if (KSEG / f"s{s:03d}.json").exists()]
    bad, nb = [], 0
    for s in pages:
        rec = page_breaks(s)
        data[f"s{s:03d}"] = rec
        nb += len(rec["starts"])
        if rec.get("mismatch"):
            bad.append(f"s{s:03d} ({rec['column_lines']} column lines, {rec['lines']} text lines)")
    OUT.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(pages)} pages, {nb} paragraph starts; {len(bad)} pages with a line-count mismatch (no breaks):")
    for b in bad:
        print("  ", b)


if __name__ == "__main__":
    if sys.argv[1] == "segment":
        segment(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    else:
        breaks([int(x) for x in sys.argv[2:]])
