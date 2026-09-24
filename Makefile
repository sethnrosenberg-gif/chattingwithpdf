PY ?= python

.PHONY: refresh seeds install
install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m playwright install chromium
seeds:
	$(PY) -m radar verify-seeds
refresh:
	$(PY) -m radar refresh
