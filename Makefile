# Every target is reproducible from a clean checkout: `make` fetches the pinned
# pandoc, runs all four pandoc lanes, and regenerates the report.
PANDOC     ?= ./vendor/pandoc/bin/pandoc
PORT       ?= 3033
SERVER_URL ?= http://localhost:$(PORT)/
FORMATS    := $(shell $(PANDOC) --list-output-formats 2>/dev/null | tr '\n' ',' | sed 's/,$$//')
# Round-trip lanes need a format pandoc can both write and read. Excluded from
# that intersection:
#   biblatex, bibtex, csljson  bibliography databases - they carry references,
#                              not documents, so a probe about tables is noise
#   json, xml                  pandoc's own AST serializations - lossless by
#                              construction, and `native` already sits in the
#                              chart as the reference row
READABLE   := $(shell python3 src/formats.py 2>/dev/null)

.PHONY: all pandoc lanes report carve clean check controls

all: pandoc lanes report

pandoc:
	./scripts/fetch-pandoc.sh

lanes: results/formats.json results/matrix.json results/roundtrip.json \
       results/exact.json results/meta.json

# The format inventory the report quotes, captured while pandoc is still in hand.
results/formats.json:
	PANDOC=$(PANDOC) python3 src/formats.py --dump

results/matrix.json:
	@echo "starting pandoc server on port $(PORT)"
	@$(PANDOC) server --port $(PORT) & echo $$! > .server.pid; sleep 3; \
	  PANDOC_SERVER=$(SERVER_URL) python3 src/run_matrix.py "$(FORMATS)" > $@; \
	  st=$$?; kill `cat .server.pid` 2>/dev/null; rm -f .server.pid; exit $$st

results/roundtrip.json:
	PANDOC=$(PANDOC) python3 src/run_roundtrip.py "$(READABLE)" > $@

results/exact.json:
	PANDOC=$(PANDOC) python3 src/run_exact.py "$(READABLE)" > $@

results/meta.json:
	PANDOC=$(PANDOC) python3 src/run_meta.py "$(READABLE)" > $@

# Opt-in: the Carve lanes are not pandoc formats and are excluded by default.
carve: results/probes.json
	CARVE_BRIDGE=$(CARVE_BRIDGE) node src/run_carve.mjs

results/probes.json:
	python3 src/dump_probes.py

report: results/formats.json
	python3 src/gen_report.py
	python3 src/gen_overview.py
	@command -v google-chrome >/dev/null && $(MAKE) docs/report.pdf docs/overview.png || \
	  echo "(no chrome found - skipped the pdf and png)"

docs/report.pdf: docs/index.html
	google-chrome --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
	  --print-to-pdf=$(CURDIR)/$@ "file://$(CURDIR)/docs/index.html"

docs/overview.png: resources/overview.html
	google-chrome --headless --disable-gpu --no-sandbox --hide-scrollbars \
	  --force-device-scale-factor=2 --window-size=1080,1180 \
	  --screenshot=$(CURDIR)/$@ "file://$(CURDIR)/resources/overview.html"

# Not part of the grid: they check that the writer lane's comparison means what
# the report says it means. See src/controls.py.
controls:
	@echo "starting pandoc server on port $(PORT)"
	@$(PANDOC) server --port $(PORT) & echo $$! > .server.pid; sleep 3; \
	  PANDOC=$(PANDOC) PANDOC_SERVER=$(SERVER_URL) python3 src/controls.py; \
	  st=$$?; kill `cat .server.pid` 2>/dev/null; rm -f .server.pid; exit $$st

check:
	PYTHONPATH=src python3 -c "import probes; print(len(probes.PROBES), 'probes load')"
	python3 -m json.tool results/matrix.json > /dev/null && echo "matrix.json valid"

clean:
	rm -f results/*.json docs/index.html
