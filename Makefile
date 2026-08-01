# Welyne HR — dev shortcuts. Runs inside the docker compose stack.

.PHONY: test test-api test-worker evals evals-judge lint migrate

# --- Tests ---
test: test-api test-worker

test-api:
	docker compose exec -T api pytest

test-worker:
	docker compose exec -T -e WHATSAPP_TOKEN= -e WHATSAPP_PHONE_ID= -e SMTP_USER= -e SMTP_PASS= \
		worker sh -c 'cd /w && python -m pytest'

# --- A4 / §5.4 evaluation harness ---
# Offline: deterministic scorer over the synthetic golden set (no LLM needed).
evals:
	docker compose exec -T -e EVALS_GOLDEN=/evals/golden/fixtures.json -e EVALS_REPORTS=/evals/reports \
		worker python -m orchestrator.evals --stub

# Real A4 judge over the golden set (needs provider keys + the full corpus).
evals-judge:
	docker compose exec -T -e EVALS_GOLDEN=/evals/golden/fixtures.json -e EVALS_REPORTS=/evals/reports \
		worker python -m orchestrator.evals

# A5 scripted-dialogue eval (spec AC: 80% of 20 complete without human help).
# Offline heuristics — exercises the harness itself without the LLM.
evals-dialogues:
	docker compose exec -T -e EVALS_DIALOGUES=/evals/golden/dialogues.json -e EVALS_REPORTS=/evals/reports \
		worker python -m orchestrator.evals --dialogues --stub

# The real measurement: drives the live A5 interpreters (needs provider keys).
evals-dialogues-live:
	docker compose exec -T -e EVALS_DIALOGUES=/evals/golden/dialogues.json -e EVALS_REPORTS=/evals/reports \
		worker python -m orchestrator.evals --dialogues

lint:
	docker compose exec -T api ruff check app
	docker compose exec -T worker sh -c 'cd /w && ruff check orchestrator'

migrate:
	docker compose exec -T api alembic upgrade head
