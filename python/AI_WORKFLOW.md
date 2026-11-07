# AI workflow

## Tools and setup

| Piece | Value |
|---|---|
| Rules and skills | [festum/ai-rules](https://github.com/festum/ai-rules) |
| Agent harness | OMP 18.18.0 (`omp --version`) |
| Planner | Copilot GPT-Sol-6.1 |
| Executor | OpenCode-Go DeepSeek-v4.1Flash |
| Runtime | uv 0.11.29, CPython 3.12.15 |
| Verification | `unittest`, `pytest`, Testcontainers PostgreSQL 16, Docker Compose |

Install and check the harness:

```sh
curl -fsSL https://omp.sh/install | sh
omp --version
omp login
```

Start OMP inside the repository root. The session reads `python/ai-rules.md` with its read tool before the first edit; that file holds the repository rules: preserved `TimeDeposit` and `update_balance` contract, calculator arithmetic and eligibility boundaries, the two allowed endpoints, application ports for HTTP and PostgreSQL, behavior tests before calculator refactoring, no upstream push, and reporting only observed checks.

Model selection stays in the harness configuration, not in this repository. To reproduce the documented pairing, pass both roles explicitly:

```sh
omp --plan bifrost/copilot/smart --model bifrost/opencode-go/smart
```

The gateway resolves those selectors to the model names above: `bifrost/copilot/smart` is aliased to `gpt-6.1-sol` and `bifrost/opencode-go/smart` to `deepseek-v4.1-flash`, both confirmed against the gateway's `/v1/models` listing. This machine's configured default executor selector is `bifrost/opencode-go/main`, which resolves to `mimo-v2.6-flash`; passing `--model` is what pins the executor to DeepSeek. Never overwrite the harness default model to force the pairing.

## Task prompt

The work reproduced by this setup:

> Implement the XA Bank time deposit take-home kata in Python. Remove the non-Python language implementations, keep the shared `TimeDeposit` class and `update_balance` signature and arithmetic unchanged, add exactly two REST endpoints (`GET /time-deposits`, `POST /time-deposits/update-balances`), persist deposits and withdrawals in PostgreSQL behind repository and unit-of-work ports, export an OpenAPI contract, demonstrate it through Swagger UI, and document the AI workflow. Write behavior tests before refactoring the calculator, verify with Testcontainers PostgreSQL and Docker Compose, and report only checks that ran.

## What was AI-assisted

| Area | Assistance | Why |
|---|---|---|
| Requirements inspection | Compared the README schema, plan rates, and constraints against the starter code | Confirms the eligibility boundaries and the exact final rounding expression before any edit |
| Boundary tests | Drafted the eligibility table, rounding cases, compounding, in-place mutation, generator input, and batch isolation | Literal expected values from the README were cross-checked against the untouched starter |
| Policy refactor | Replaced the nested conditional with `MonthlyInterestPolicy` and a registry | Smaller diff than three class hierarchies, and the calculator keeps one rounding site |
| Persistence | Wrote the schema, seed data, Psycopg adapter, and unit of work | Repetitive SQL and mapping code; human review decided the row-lock and transaction semantics |
| API and contract | Wrote the FastAPI adapter, response models, OpenAPI exporter, and Swagger proxy | Mechanical mapping between application records and wire models |
| Test review | Reviewed failures and re-ran suites | Acceptance came from observed output, not from generated code |

## Observed checks

```sh
cd python
uv sync --locked
uv run python -m unittest -v test_time_deposit
uv run pytest -q tests/test_interest_extension.py
uv run pytest -q tests/test_api.py
uv run pytest -q
uv run pytest -q --cov-report=xml --cov-report=term-missing
```

`unittest` ran 9 tests before the calculator refactor (expected values cross-checked against the untouched starter) and again after it, both `OK`. The extension test passed once the policy seam existed. `uv run pytest -q` ran 35 tests plus 31 subtests: 25 of them against a Testcontainers PostgreSQL 16 instance, the rest covering the calculator, the policies, the exporter, and the default `DATABASE_URL` wiring.

`uv run pytest -q` now runs with branch coverage by default (`addopts` in `pyproject.toml`) over `api`, `application`, `export_openapi`, `interest_policies`, `postgres`, and `time_deposit`: 199 statements, 24 branches, 100% covered, `Required test coverage of 95.0% reached`. Running a single test file fails the gate as intended: `uv run pytest -q tests/test_interest_extension.py` ends with `FAIL Required test coverage of 95.0% not reached. Total coverage: 55.21%` and exit status 1, so a partial run cannot pass silently.

`.github/workflows/ci.yml` was rehearsed locally step by step: `uv sync --locked`, the coverage run with `--cov-report=xml`, and `uv run coverage report --format=markdown --fail-under=0` for the job summary all behaved as in the workflow. The Compose job's commands were executed against a fresh volume: `docker compose -f ../compose.yaml up --build -d`, the readiness loop, five seeded deposits, `POST` → `204`, `[1201.0, 1203.0, 1205.0, 1200.0, 1200.0]` after one accrual, `200` from `http://localhost:8080/openapi.json`, then `down -v`. The workflow file passes `actionlint` with no findings; the run on GitHub itself has not happened because nothing was pushed.

The Compose stack was then built and started, and the endpoints exercised over HTTP: `GET` returned the five fixtures, `POST` returned `204 No Content` with an empty body, the next `GET` returned `[1201.0, 1203.0, 1205.0, 1200.0, 1200.0]`, and a second `POST` returned `[1202.0, 1206.01, 1210.02, 1200.0, 1200.0]`. After `docker compose restart api db` the balances were unchanged, so the data survived. Swagger UI served `200` at port 8080, `/openapi.json` matched the repository contract, and both proxied paths answered through 8080 (`200` and `204`).

The money-precision pass was verified the same way against a fresh volume. `\d "timeDeposits"` reported `balance | numeric(18,5)` with `time_deposits_balance_range CHECK (balance >= '-1000000000000'::bigint::numeric AND balance <= '1000000000000'::bigint::numeric)`, `POST` returned `204`, and the next `GET` returned `[1201.0, 1203.0, 1205.0, 1200.0, 1200.0]`. Inserting a sixth deposit at `999999999999.99` and posting again returned `409` with `{"detail":"balance limit exceeded","message":"accrual would move deposits [6] outside the stored range -1000000000000..1000000000000","depositIds":[6]}`, and `SELECT id, balance` showed all six balances unchanged, so the batch rolled back as designed.

The refactor was also checked against the original implementation directly: `git show HEAD:python/time_deposit.py` was executed in a scratch namespace and both calculators were run over 876,015 generated combinations of plan strings, balances, and day counts, plus 24 successive accrual rounds on four deposits. Balances and untouched `days` matched in every case, so the characterization suite and the exhaustive comparison agree.

## Fault detection

Each variant was applied alone, the suite rerun, and the code restored:

| Variant | Observed failure |
|---|---|
| `basic` minimum `>30` to `>29` | `basic`/30 accrued: `1200.0 != 1201.0`, and the ineligible rounding case became `2.67 != 2.68` |
| `student` maximum `<366` to `<367` | `student`/366 accrued: `1200.0 != 1203.0`, plus a batch mismatch `[1205.0, 1200.0, 1200.0, 1201.0] != [1205.0, 1200.0, 1203.0, 1201.0]` |
| `premium` minimum `>45` to `>44` | `premium`/45 accrued: `1200.0 != 1205.0` |
| Rounding interest before adding it to the balance | `100.09 != 100.08` |
| Skipping the final rounding for zero interest | `2.67 != 2.675` |

Every variant was caught, so no test needed strengthening.

## Corrections during the session

- The first policy module was written with a registry entry outside the dictionary by mistake; the file failed to parse and was rewritten in full instead of patched.
- A boundary-variant loop initially appeared to leak between runs because stale `__pycache__` files survived a rewrite with identical byte length. Running with `PYTHONDONTWRITEBYTECODE=1 uv run python -B` and clearing caches made each variant report its own assertion.
- The exported contract's `204` response carries no `content` key at all; the test asserts absence rather than an empty mapping.
- `testcontainers.postgres` is deprecated in 4.15.0; the import uses `testcontainers.community.postgres`.

## Reproducing

1. `uv sync --locked` inside `python/`.
2. `uv run export_openapi.py` to regenerate `openapi.json`.
3. `uv run pytest -q` for the unit and Testcontainers suites (Docker required); the run fails below 95% branch coverage.
4. `docker compose up --build -d` at the repository root for the demo, then follow the README curl and Swagger steps.
5. `.github/workflows/ci.yml` repeats 3 and 4 on GitHub, splitting them into a test job and a Compose smoke job.

Secrets stay out of this document and out of the repository; the demo Compose stack uses local-only credentials for a throwaway database.
