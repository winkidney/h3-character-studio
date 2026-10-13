PYTHON ?= python3.12
.PHONY: install test wheel
install:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install .
test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
wheel:
	$(PYTHON) -m pip wheel --no-deps . -w dist
