# Building Hack 1337

## Quick start

```sh
brew install uv fontforge harfbuzz   # macOS; on Debian/Ubuntu: apt install fontforge python3-fontforge libharfbuzz-bin, plus uv
make fonts      # download pinned upstreams, build ttf/ otf/ woff/ woff2/   (~1 min)
make check      # verify ligatures, metrics, icon coverage; compare with the committed fonts
make previews   # re-render preview/*.png and docs/ligatures.md
```

Everything downloaded or generated goes into `build/` (git-ignored). Upstream versions and their
sha256 checksums are pinned in [`scripts/config.py`](../scripts/config.py).

## Pipeline

`scripts/build.py` runs these steps for each style, in parallel:

| Step | Script | What it does |
| --- | --- | --- |
| 1 | `prepare.py` | Takes stock **Hack 3.003** and applies the Hack 1337 line metrics (see below). |
| 2 | Nerd Fonts `font-patcher` (run by fontforge) | Adds every **Nerd Fonts 3.5.1** icon set as single-width glyphs (`--complete --mono --metrics HHEA`). Icons and Powerline separators are fitted to the 1337 cell height. |
| 3 | `native.py` | Draws the ligatures from `src/ligatures/recipes.py` and generates their substitution rules. |
| 4 | `features.py` | Compiles `src/features/native.fea` (stylistic sets) together with the ligature rules. |
| 5 | `finalize.py` | Sets names, version and license strings, restores the Windows metrics, and checks that every glyph has the same advance width. |
| 6 | `export.py` | Writes `.otf` (CFF outlines), `.woff` and `.woff2` from the `.ttf`. |

The build only uses [fontTools](https://github.com/fonttools/fonttools),
[skia-pathops](https://github.com/fonttools/skia-pathops) and the official Nerd Fonts patcher.
Nothing from another font is built in: the ligatures are drawn from Hack's own strokes.

## Ligatures (`src/ligatures/recipes.py`)

### Drawing

Each ligature is a small Python recipe. It gets a `Kit` for the style being built and returns the
outline, drawn across the ligature's cells:

```python
@ligature("==")
def _(k):
    return _bars(k, "=", 2)          # Hack's '=' bars, stretched across two cells
```

- **Parts and measurements** come from the style's own glyphs: `k.glyph("=")`, `k.bands("≡")`
  (the bars' heights), `k.stroke` (thickness of `-`), `k.bar_width` (thickness of `|`),
  `k.axis` (centre of `= < >`). One recipe therefore gives the right weight in Regular and Bold.
- **Boolean operations** (skia-pathops) merge overlapping parts into clean outlines.
- **Tightened sequences** (`TIGHT`): Hack's glyphs moved closer (`## :: {{ <$> ?:` …), never so
  close that they collide in Bold; `*`, `:` and `.` can be centred on the math axis.
- **Arrows** come from one parametric builder: a shaft (`-`, `=`, or `~`, a sine wave with the
  height and weight of Hack's `~`) plus an end piece on each side (`head`, `head2`, `tail`,
  `tail2`, `bar`, `bar2`). The `ARROWS` table maps every arrow sequence to its spec, e.g.
  `">->": ("-", "tail", "head")`. Heads are drawn by `_head()`: a mitred chevron with Hack's
  stroke, as tall as Hack's `>` but steeper (`HEAD_ANGLE`). Hack's own `>` is too flat to work as
  an arrowhead.
- **Italics:** Hack Italic keeps most operators upright (`= < > | . ~ ≤ ≥ ≠ ≡`), so recipes use
  the italic glyphs as they are. Only the arrow shafts get slanted ends, matching the italic `-`.

Like most programming fonts, a ligature keeps one glyph per character: `->` becomes an empty
spacer (`LIG`) followed by one glyph that is drawn leftwards over the spacer. Cursor movement and
selection keep working character by character.

### When ligatures form

`native.py` generates the rules from the recipes (see its docstring):

- **Leftmost-longest**, like a tokenizer: one lookup scans the line left to right and at each
  position forms the longest ligature that starts there. `<=<=` is `<=` `<=`; `->=>` is `->` `=>`.
- **Not inside runs:** by default a ligature doesn't form inside a longer run of its first or
  last character, so `====` stays plain. `plain_runs=False` turns that off (e.g. `}}}}` pairs up).
- **Exceptions**, written at the bottom of `recipes.py` as `BEFORE⟨SEQUENCE⟩AFTER` patterns:
  - `GIVE_WAY`: when two ligatures overlap, which one wins (`#=` gives way in Ruby's `#=>`).
  - Context rules: no ligature where it would mislead, e.g. `<-` in time zones (`<-04>`), `/**`
    in globs (`/**/*.py`), comparisons in regex lookarounds (`(?<=`).
  - `only=`: ligatures that form only in a given context (`/\` in ASCII art).

JetBrains Mono's rules are the behavioural reference, because they're well tested. `make check`
shapes the real-world snippets in `tests/code-samples.txt` with both fonts. The ligatures must
form in exactly the same places, except for the lines in `tests/accepted-differences.txt`
(each with a reason). JetBrains Mono is downloaded for this test only.

Two dev tools help when changing rules (both compare with JetBrains Mono):

- `uv run python scripts/corpusdiff.py PATH…` shapes every line of real source code under the given
  directories and lists the differences, most frequent first. On a million lines of Python,
  Ruby, C, shell and JS/TS, about 10 lines differ, all deliberately.
- `uv run python scripts/rulediff.py` checks every 2–4 character combination of operator
  characters. The remaining differences are combinations that don't occur in real code.

### Stylistic sets (`src/features/`)

`native.fea` holds Hack 1337's own OpenType code. Its lookups run *before* the ligature rules, so
they can switch ligatures off. Two conveniences:

- `$u003C` in `native.fea` stands for "the glyph for U+003C in this font". The Nerd Fonts patcher
  renames glyphs, so don't hard-code names.
- `glyphs.json` declares extra glyphs as aliases of existing characters (e.g. `less.ss01` looks
  like `<`). The ligature rules don't match aliases, which is how `ss01` keeps comparison
  operators plain.

### Line metrics

Hack 1337 has a tighter line height than stock Hack. In `hhea` and `OS/2` typo, ascent/descent
are 1556/−492 with no line gap, which is exactly 1 em. macOS and most Linux apps use these
values. `usWinAscent`/`usWinDescent` keep Hack's 1901/483, so Windows spacing is unchanged and
accents are never clipped. Change `LINE_METRICS` in `config.py` to adjust.

## Updating upstreams

Bump the version, URL and sha256 in `scripts/config.py`, then run `make fonts check`. To get a
checksum, run `shasum -a 256` on the downloaded zip. If a new JetBrains Mono release adds
ligatures, `make check` lists them as missing; add a recipe for each.

## History: how 1.x was made

Hack 1337 1.x (2021) was made by hand, with no build scripts:

1. Started from **Hack Nerd Font Mono** as released by Nerd Fonts **2.1**.
2. Added Fira Code **3.1** ligatures (124) with [Ligaturizer](https://github.com/ToxicFrog/Ligaturizer).
3. Edited in **FontLab 7**: set the `hhea`/typo metrics to 1556/−492 (line gap 0), and redrew the
   Powerline glyphs `U+E0A0–E0A2` and `U+E0B0–E0B3` to fit that line height with a little
   overlap, so powerlevel10k segments show no seams.

2.0 rebuilds the same idea from scratch. It keeps the line metrics. It drops the hand-drawn
Powerline glyphs, because Nerd Fonts 3 fits them to the cell itself. It replaces the copied
Fira Code ligatures with ones drawn from Hack's own strokes. The set follows JetBrains Mono's
(32 more than 1.x, e.g. `&&` `|->` `<==>` `/**` `;;;` `{{` `}}`) plus Fira's `~=` and `..=`.
Four 1.x ligatures are gone: `www` `**` `%%` `.-`.
