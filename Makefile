PYTHON := .venv/Scripts/python.exe
BNB    := bnb_arb_agent

.PHONY: run test dashboard mcp lint

run:
	$(PYTHON) $(BNB)/orchestrator.py

test:
	$(PYTHON) -m pytest $(BNB)/tests/ -v --tb=short

dashboard:
	$(PYTHON) -m streamlit run $(BNB)/dashboard.py

mcp:
	powershell -ExecutionPolicy Bypass -File start_mcp.ps1

lint:
	$(PYTHON) -m ruff check $(BNB)/
