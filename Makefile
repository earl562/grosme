.PHONY: setup run lint clean test check-ollama format run-image run-text

setup:
	uv sync
	@echo "Checking Ollama..."
	@ollama list | grep -q "lfm2.5-thinking" || ollama pull lfm2.5-thinking:1.2b
	@echo "Setup complete."

run:
	uv run python main.py

run-image:
	uv run python main.py --input input/

run-text:
	uv run python main.py --text "milk, eggs, bread, chicken breast"

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

test:
	uv run pytest tests/ -v

check-ollama:
	@ollama list | grep -q "lfm2.5-thinking" && echo "Model ready" || echo "Run: ollama pull lfm2.5-thinking:1.2b"

clean:
	rm -rf output/*.json __pycache__ .pytest_cache
