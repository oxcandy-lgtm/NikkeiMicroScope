.PHONY: help test validate-fixtures compile-check

help:
	@echo "NikkeiMicroScope - local development targets"
	@echo "  make test              Run the stdlib unittest suite"
	@echo "  make compile-check     Run python3 -m compileall on nms and tests"
	@echo "  make validate-fixtures Run the read-only fixture validation script"

compile-check:
	python3 -m compileall -q nms tests

test:
	python3 -m unittest discover -s tests -v

validate-fixtures:
	bash scripts/validate-fixtures.sh
