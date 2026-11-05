# Hack 1337 build. Requirements: uv, fontforge, harfbuzz (hb-view, for previews).
#   brew install uv fontforge harfbuzz
PY := uv run python

.PHONY: fonts fetch check previews clean

fonts:            ## build all styles into ttf/ otf/ woff/ woff2/
	$(PY) scripts/build.py

fetch:            ## download pinned upstream releases into build/cache
	$(PY) scripts/fetch.py

check:            ## verify the built fonts (ligatures, metrics, coverage)
	$(PY) scripts/check.py

previews:         ## render preview images into preview/
	$(PY) scripts/preview.py

clean:
	rm -rf build/work
