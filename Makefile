# Hack 1337 build. Requirements: uv and fontforge; node for `make previews`.
#   brew install uv fontforge node
PY := uv run python

.PHONY: fonts fetch check previews clean

fonts:            ## build all styles into ttf/ otf/ woff/ woff2/
	$(PY) scripts/build.py

fetch:            ## download pinned upstream releases into build/cache
	$(PY) scripts/fetch.py

check:            ## verify the built fonts (ligatures, metrics, coverage)
	$(PY) scripts/check.py

previews: node_modules  ## render preview images into preview/
	uv run --group previews python scripts/preview.py

node_modules: package-lock.json
	npm ci --silent
	touch node_modules

clean:
	rm -rf build/work
