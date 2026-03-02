.PHONY: setup run lint clean test check-ollama format run-text uat uat-query uat-memo demo notify-test benchmark

setup:
	uv sync
	uv run scrapling install
	@echo "Checking Ollama..."
	@ollama list | grep -q "lfm2.5-thinking" || ollama pull lfm2.5-thinking:1.2b
	@echo "Setup complete."

run:
	uv run python main.py

run-text:
	uv run python main.py --text "milk, eggs, bread, chicken breast"

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

test:
	uv run pytest tests/ -v

uat:
	uv run python tests/uat_runner.py

uat-query:
	uv run python tests/uat_runner.py --query

uat-memo:
	uv run python tests/uat_runner.py --memo

check-ollama:
	@ollama list | grep -q "lfm2.5-thinking" && echo "Model ready" || echo "Run: ollama pull lfm2.5-thinking:1.2b"

demo:
	uv run python main.py --text "Eggland's Best Eggs 18 ct, Driscoll's Strawberries 1 lb, Whole Milk Gallon"

notify-test:
	uv run python main.py --text "milk, eggs, bread" --notify

benchmark:
	uv run python benchmarks/accuracy.py

clean:
	rm -rf output/*.json __pycache__ .pytest_cache
