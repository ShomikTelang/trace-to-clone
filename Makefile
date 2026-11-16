.PHONY: install install-all reference-up reference-down generate demo test smoke gui record infer
install:
	python -m pip install -e '.[test]'
install-all:
	python -m pip install -e '.[all]'
	python -m playwright install chromium
reference-up:
	docker compose -f reference/compose.yml up -d
reference-down:
	docker compose -f reference/compose.yml down
generate:
	python -m traceclone generate
demo:
	python -m traceclone demo
test:
	python -m pytest -q
smoke:
	python -m traceclone evaluate --url http://localhost:8000
gui:
	python -m traceclone evaluate --url http://localhost:8000 --gui --screenshot artifacts/gui_smoke.png
record:
	python -m traceclone record --url http://localhost:8081 --headed --storage-state reference/storage-state.json --out artifacts/reference_trace
infer:
	python -m traceclone infer --trace artifacts/reference_trace/trace.json --out artifacts/inference_draft.json
