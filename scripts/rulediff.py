"""Dev tool: compare when ligatures form in Hack 1337 vs JetBrains Mono (the reference).

Shapes every 2-4 character combination of the characters that occur in ligatures (plus a few
neighbours) with both fonts, reduces every difference to its shortest form, and prints them
grouped by ligature. Used to write the `ignore=` exceptions in src/ligatures/rules.py.

Usage: rulediff.py [STYLE]
"""
import itertools
import sys
from collections import defaultdict

from check import Shaper, _ligs
from config import CACHE, FAMILY, ROOT, STYLES
from native import load_recipes

EXTRA = " .0a"  # neighbours that matter: spaces, dots, digits, letters


def differs(jbm, new, s):
    return set(_ligs(jbm, s)) != set(_ligs(new, s))


def minimal(jbm, new, s):
    """Shrink s from both ends while the difference persists."""
    changed = True
    while changed and len(s) > 2:
        changed = False
        for t in (s[1:], s[:-1]):
            if len(t) >= 2 and differs(jbm, new, t):
                s, changed = t, True
                break
    return s


def main(style: str) -> None:
    jbm = Shaper((CACHE / "jetbrains-mono" / "fonts" / "ttf" / STYLES[style]["jbm"]).read_bytes())
    new = Shaper((ROOT / "ttf" / f"{FAMILY} {style}.ttf").read_bytes())
    recipes = load_recipes()
    skip = [seq for seq, r in recipes.items() if r.glyph_name not in set(jbm.order)]
    chars = sorted({c for seq in recipes for c in seq} | set(EXTRA))
    found = set()
    for n in (2, 3, 4):
        for t in itertools.product(chars, repeat=n):
            s = "".join(t)
            if any(x in s for x in skip) or not differs(jbm, new, s):
                continue
            found.add(minimal(jbm, new, s))
    groups = defaultdict(list)
    for s in sorted(found, key=lambda s: (len(s), s)):
        a, b = set(_ligs(jbm, s)), set(_ligs(new, s))
        ours = sorted(g for _, g in b - a)
        theirs = sorted(g for _, g in a - b)
        groups[(tuple(ours), tuple(theirs))].append(s)
    print(f"{len(found)} minimal differences")
    for (ours, theirs), samples in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"ours {list(ours)} vs JBM {list(theirs)}: {' '.join(repr(x) for x in samples[:12])}"
              + (f" … (+{len(samples) - 12})" if len(samples) > 12 else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Regular")
