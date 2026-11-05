.PHONY: test test-backend test-frontend

# backend + frontend tests (no browser, no docker)
test: test-backend test-frontend

# pytest — FastAPI routes against in-memory SQLite
test-backend:
	uv run --group test pytest

# vitest — component / unit tests (happy-dom)
test-frontend:
	cd frontend && npm run test
