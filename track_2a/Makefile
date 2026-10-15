.PHONY: run check-config test

run:
	docker compose --env-file /dev/null run --build --rm app

check-config:
	docker compose --env-file /dev/null run --build --rm \
		-e LLM_NAME -e LLM_BASE_URL -e LLM_API_KEY app check-config

test:
	uv run --frozen pytest -q
