PYTHON ?= python3
WORDS ?=

.PHONY: help test snapshots preview compact lint dictionary clean

help:            ## Show this help.
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) \
	  | sed -E 's/:.*## /\t/' | expand -t 16

test:            ## Run the tests (a fraction of a second).
	$(PYTHON) -m unittest discover -s tests -t tests

snapshots:       ## Endorse the current markup as the new reference.
	$(PYTHON) tests/snapshots.py

preview:         ## Render a few entries in light and dark, and open them.
	$(PYTHON) preview.py $(WORDS) --open

compact:         ## Same preview, in the right-click window.
	$(PYTHON) preview.py $(WORDS) --compact --open

lint:            ## Run ruff over the repository.
	ruff check . && ruff format .

dictionary:      ## Build the dictionary from the full volumes.
	$(PYTHON) jibiki_dict.py

clean:           ## Remove build products.
	rm -rf build preview.html tests/__pycache__ __pycache__
