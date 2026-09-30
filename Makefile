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

.PHONY: all pandoc lanes stamp report dashboard delta carve carve-rt clean check controls correctness

# The lanes are I/O bound on pandoc itself and gain nothing from -j, and the
# stamp has to be written before the run it describes. Serial by declaration
# rather than by luck.
.NOTPARALLEL:

# A lane writes through `> $@`, so a crash leaves a truncated file behind that
# the next make reads as a finished measurement. Delete it instead.
.DELETE_ON_ERROR:

# Which results set a delta is judged against, and under which threshold
# profile. The defaults are the pair CI uses: this checkout's committed results
# against a fresh run of the same pinned pandoc, where nothing may move.
BASELINE  ?= results-baseline
CANDIDATE ?= results
PROFILE   ?= pin

all: pandoc lanes report

pandoc:
	./scripts/fetch-pandoc.sh

LANE_FILES := results/formats.json results/matrix.json results/roundtrip.json \
              results/exact.json results/meta.json

# -B, because the lane files are committed. A checkout has all of them, so make
# reads every measurement as up to date and `make lanes` does nothing but
# rewrite the stamp - which is how the nightly watch came to label the pinned
# results as a nightly run, and how the staleness gate came to compare a file
# against itself. Asking for `lanes` means measure, not "measure if the file is
# missing"; `report` still depends on the files themselves, so it stays
# runnable from an existing results/ with no pandoc in hand.
#
# `stamp` is phony and runs first: every measurement records which pandoc
# produced it, and a stamp make skipped as up to date would date the results to
# whenever the file was last written.
lanes: stamp
	$(MAKE) -B $(LANE_FILES)

stamp:
	PANDOC=$(PANDOC) python3 src/run_env.py

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

# The other direction: Carve source in, Carve source out. Also opt-in.
carve-rt:
	CARVE_BRIDGE=$(CARVE_BRIDGE) node src/run_carve_rt.mjs

results/probes.json:
	python3 src/dump_probes.py

report: results/formats.json dashboard
	python3 src/gen_report.py
	python3 src/gen_overview.py
	@command -v google-chrome >/dev/null && $(MAKE) docs/report.pdf docs/overview.png || \
	  echo "(no chrome found - skipped the pdf and png)"

# The dated page: which pandoc, measured when, what moved since the baseline.
# Reads results/ only, so it needs no pandoc and no network.
dashboard:
	python3 src/gen_dashboard.py

# What moved between two results sets, gated by thresholds.json. Fails the
# build on a breach; add --exit-zero through DELTA_ARGS for a report-only run.
delta:
	python3 src/delta.py --baseline $(BASELINE) --candidate $(CANDIDATE) \
	  --profile $(PROFILE) --json results/delta.json $(DELTA_ARGS)

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

correctness:
	PANDOC=$(PANDOC) python3 src/epub_order.py

check:
	PYTHONPATH=src python3 -c "import probes; print(len(probes.PROBES), 'probes load')"
	python3 -m json.tool results/matrix.json > /dev/null && echo "matrix.json valid"
	PYTHONPATH=src python3 src/severity.py
	PYTHONPATH=src python3 -m unittest discover -s tests -t .

clean:
	rm -f results/*.json docs/index.html docs/dashboard.html
