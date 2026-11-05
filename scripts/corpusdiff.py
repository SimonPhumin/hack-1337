"""Dev tool: compare where ligatures form in Hack 1337 vs JetBrains Mono on real source code.

Collects lines containing ligature characters from the given files/directories, shapes each
distinct line with both fonts and reports the differences grouped by ligature, most frequent
first. Unlike rulediff.py (every 2-4 character combination), this shows what readers see.

Usage: corpusdiff.py PATH [PATH ...] [--style Regular] [--limit 200000]
"""
import argparse
import os
from collections import Counter, defaultdict
from pathlib import Path

from check import Shaper, _ligs
from config import CACHE, FAMILY, ROOT, STYLES
from native import load_recipes

EXTS = {".py", ".rb", ".h", ".c", ".js", ".ts", ".tsx", ".go", ".rs", ".swift", ".sh", ".hs",
        ".ex", ".exs", ".kt", ".java", ".php", ".html", ".css", ".md", ".lua", ".ml"}


def lines(paths, chars, limit):
    seen = set()
    for root in paths:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__"}]
            for f in files:
                if Path(f).suffix not in EXTS:
                    continue
                try:
                    text = Path(dirpath, f).read_text(errors="ignore")
                except OSError:
                    continue
                for line in text.splitlines():
                    line = line.strip()[:200]
                    if line and line not in seen and any(c in chars for c in line):
                        seen.add(line)
                        yield line
                        if len(seen) >= limit:
                            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--style", default="Regular")
    ap.add_argument("--limit", type=int, default=200_000)
    a = ap.parse_args()
    jbm = Shaper((CACHE / "jetbrains-mono" / "fonts" / "ttf" / STYLES[a.style]["jbm"]).read_bytes())
    new = Shaper((ROOT / "ttf" / f"{FAMILY} {a.style}.ttf").read_bytes())
    recipes = load_recipes()
    skip = [s for s, r in recipes.items() if r.glyph_name not in set(jbm.order)]
    chars = {c for s in recipes for c in s}
    total = differing = 0
    groups = defaultdict(Counter)
    for line in lines(a.paths, chars, a.limit):
        total += 1
        x, y = set(_ligs(jbm, line)), set(_ligs(new, line))
        if x == y:
            continue
        if any(s in line for s in skip) and all(any(g == recipes[s].glyph_name for _, g in y - x) for s in skip if s in line):
            continue
        differing += 1
        for i, g in y - x:
            groups[f"ours {g}"][line] += 1
        for i, g in x - y:
            groups[f"JBM  {g}"][line] += 1
    print(f"{differing} of {total} lines differ")
    for label, c in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"{sum(c.values()):5}  {label}:  " + "  |  ".join(l[:70] for l, _ in c.most_common(3)))


if __name__ == "__main__":
    main()
