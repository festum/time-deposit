# Time Deposit Refactoring Kata - Take-Home Assignment

## XA Bank Time Deposit

### Context
A junior developer implemented domain logic for a time deposit system but did not complete the API functionality. Your task is to refactor the existing codebase to implement all required functionalities based on the provided business requirements, ensuring no breaking changes occur.

### Requirements

1. **API Endpoints**:
    - Create a RESTful API endpoint to update the balances of all time deposits in the database.
    - Create a RESTful API endpoint to retrieve all time deposits.
        - The GET endpoint should return a list of all time deposits with the following schema:
            - `id`
            - `planType`
            - `balance`
            - `days`
            - `withdrawals`

2. **Database Setup**:
    - Store all time deposit plans in a database.
    - Define the following tables:
        - `timeDeposits`:
            - `id`: Integer (primary key)
            - `planType`: String (required)
            - `days`: Integer (required)
            - `balance`: Decimal (required)
        - `withdrawals`:
            - `id`: Integer (primary key)
            - `timeDepositId`: Integer (foreign key, required)
            - `amount`: Decimal (required)
            - `date`: Date (required)

3. **Interest Calculation**:
    - Implement logic to calculate monthly interest based on the plan type:
        - **Basic Plan**: 1% interest
        - **Student Plan**: 3% interest (no interest after 1 year)
        - **Premium Plan**: 5% interest (interest starts after 45 days)
    - No interest is applied for the first 30 days for any existing plans.

4. **Refactoring Constraints**:
    - Do not introduce breaking changes to the shared `TimeDeposit` class or modify the `updateBalance` method signature.
    - Ensure the design is extensible to accommodate future complexities in interest calculations.

5. **Code Quality**:
    - Adhere to SOLID principles, design patterns, and clean code practices where applicable.

6. **AI-Assisted Development**:
    - Set up an AI harness or agent workflow and use it throughout the development for this take-home exercise.
    - Briefly document the tools and setup used (e.g., LLMs, coding assistants, agentic frameworks, configuration).
    - Ensure your AI setup is practical and reproducible.
    - Include any custom rules, system prompts, or agent configurations used.
    - Include a brief summary of which parts of the solution were AI-assisted and why.

### Important Guidelines
- The existing `TimeDepositCalculator.updateBalance` method is functioning correctly. Ensure its behavior remains unchanged after refactoring.
- The final solution must include **exactly two API endpoints**. Do not develop additional endpoints.
- **Do not** create a pull request or a new branch in the ikigai-digital repository. Instead, fork the repository into your own GitHub repository and develop the solution there.
- Handling invalid input or exceptions is not required.
- Use any tools, frameworks, or libraries you find suitable.
- In case of ambiguity, make logical assumptions and justify them in code comments.

### Preferred Stack
- Use an OpenAPI Swagger contract.
- Embrace Hexagonal Architecture.
- Follow atomic commit practices.
- Utilize testcontainers.
- Leverage AI-assisted development tools for code generation, testing, and refactoring.

### Submission Instructions
- Provide clear instructions on how to trigger the endpoints using the Swagger contract.
- Email the link to your public GitHub repository.

---

## Solution

Provenance: forked from [ikigai-digital/time-deposit-take-home-kata](https://github.com/ikigai-digital/time-deposit-take-home-kata). This fork keeps Python only; the C#, Java, Kotlin, and TypeScript starters were removed.

### Layout

| Path | Role |
|---|---|
| `python/time_deposit.py` | Shared `TimeDeposit` model and `TimeDepositCalculator`, unchanged contract |
| `python/interest_policies.py` | Plan policies behind an `InterestPolicy` protocol |
| `python/application.py` | Use-case service, records, repository and unit-of-work ports |
| `python/postgres.py` | Psycopg adapters that implement the ports |
| `python/api.py` | FastAPI adapter with the two endpoints |
| `python/openapi.json` | Exported OpenAPI 3.1 contract |
| `python/sql/` | Schema and demo fixtures |
| `python/tests/` | Testcontainers PostgreSQL integration tests |
| `compose.yaml` | Database, API, and Swagger UI |

Hexagonal split: the calculator and policies know nothing about HTTP or SQL, the service depends only on the ports, and the FastAPI and Psycopg adapters are constructed at the edges.

### Prerequisites

- Docker with Compose (for the demo stack and the integration tests)
- `uv` (installed below if missing)
- Python 3.12

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Run the demo

```sh
cd python && uv sync --locked && uv run export_openapi.py && cd ..
docker compose up --build -d
```

Database `time_deposit` with the `timeDeposits` and `withdrawals` tables is created on first startup of the `time-deposit-data` volume and seeded with five deposits and three withdrawals. Later startups keep existing data and never reseed.

```sh
curl -fsS http://localhost:8000/time-deposits
curl -i -X POST http://localhost:8000/time-deposits/update-balances
curl -fsS http://localhost:8000/time-deposits
```

The first `GET` returns the fixtures, `POST` answers `204` with an empty body, and the second `GET` shows each eligible balance after one monthly accrual (`[1201.0, 1203.0, 1205.0, 1200.0, 1200.0]`). Deposits with no withdrawals return `"withdrawals": []`.

Ports 5432, 8000, and 8080 must be free. If one is taken, change the host side in `compose.yaml` and regenerate the contract with a matching server URL, for example `API_BASE_URL=http://localhost:18080 uv run export_openapi.py` from `python/`.

### Swagger

Open <http://localhost:8080>. The UI is served by its own container, so the API application itself exposes exactly the two endpoints and no `/docs`, `/redoc`, or `/openapi.json` route.

1. Expand `GET /time-deposits`, press **Try it out**, then **Execute**. The response lists every deposit.
2. Expand `POST /time-deposits/update-balances`, press **Try it out**, then **Execute**. The response is `204` with no body.
3. Repeat the `GET`. Balances show the accrual.

Try it out sends real requests to the running stack, and each successful `POST` permanently adds another accrual to the demo database. The requests go to port 8080, which proxies the two paths to the API, so no CORS preflight is involved.

The contract itself is [`python/openapi.json`](python/openapi.json); load it in any Swagger UI or render it elsewhere.

### Endpoints

| Method | Path | Response |
|---|---|---|
| `GET` | `/time-deposits` | `200` with an array of deposits |
| `POST` | `/time-deposits/update-balances` | `204`, empty body |
| `POST` | `/time-deposits/update-balances` | `409` when the accrual would leave the stored range |

`GET` returns `id`, `planType`, `balance`, `days`, and `withdrawals`; each withdrawal carries `id`, `timeDepositId`, `amount`, and `date`. Money is a JSON number, dates are `YYYY-MM-DD`. The `409` body names every offending deposit: `{"detail": "balance limit exceeded", "message": ..., "depositIds": [...]}`.

### Money precision

Both money columns are `NUMERIC(18,5)`. Eighteen digits with five fractional places is the grain of the ISO 20022 `ActiveCurrencyAndAmount` type, and finer than the 2 minor units ISO 4217 fixes for USD, EUR, and TWD. The database stores the value verbatim and returns it verbatim: it never rescales to cents and never rounds. `GET` converts `Decimal` to a JSON number unchanged, so `100.004` reads back as `100.004` and `0.00001` as `0.00001`.

Rounding happens exactly once, inside `TimeDepositCalculator.update_balance`, at the moment a `POST` accrues interest: `round(balance + interest, 2)`. That expression is the starter's own and stays byte-identical. `round` resolves exact binary ties to even, the convention ISO 80000-1 recommends for numeric values, so `150.125` becomes `150.12` rather than `150.13` (pinned by `test_cent_rounding_is_not_half_up`). Values that only look like decimal ties are first represented in binary and then rounded from that representation, which is why `2.675` becomes `2.67` (pinned by `test_ineligible_balance_is_still_rounded`). The two conventions can only disagree on inputs with three or more decimal places, and bank postings are whole minor units, so this shows up only for sub-cent balances that the schema tolerates but no real deposit carries.

`balance` and `amount` also carry `CHECK (... BETWEEN -1000000000000 AND 1000000000000)`. The bound keeps every stored amount inside the ±90,071,992,547,409.91 range where a JSON number is exact, rejects `NaN` and `±Infinity`, and stops values whose exponent overflows `NUMERIC`. A `POST` whose accrual would cross the bound is refused with `409` and rolls back the whole batch, so no deposit changes.

### Scaling limits

Measured on a local Docker Desktop PostgreSQL 16 container, one deposit per row, `GET` and `POST` through the compose stack. Each figure is the median of five runs after warm-up.

| Rows | `GET` | `POST` | `GET` body |
|---|---|---|---|
| 1,000 | 21 ms | 69 ms | 74 KB |
| 10,000 | 133 ms | 514 ms | 749 KB |
| 50,000 | 609 ms | 2.37 s | 3.8 MB |
| 205,000 | 2.88 s | 9.68 s | 17 MB, +345 MB RSS |

Result sets dominate. `GET` serializes every deposit with its full withdrawal history in one response, and `POST` rewrites every row in one transaction, so both grow linearly with the table. Fixed cost per request is 9.90 ms of connect and query.

| Scenario | Result |
|---|---|
| 200 parallel `GET` | 84 req/s, all `200` |
| Parallel `POST` at 1k rows | 16 req/s, then saturated, all `204` |
| `GET` during a 30k-row `POST` | 13 ms → 405–590 ms while the `POST` holds its locks (4.3 s) |
| 1 deposit, 100k withdrawals | `GET` 1.13 s / 6.5 MB, `POST` 0.54 s |
| Connections | one per request before pooling; `max_connections=100`, the 101st is refused |

Deliberate limits: no pagination on `GET`, no batching on `POST`, no wire format other than JSON numbers. Each is a documented boundary rather than an omission, and each has a known upgrade path (`LIMIT`/`OFFSET` plus a cursor, chunked commits, minor-unit integers). The connection pool holds `min_size=1, max_size=10` per process, reused across requests, which is why 200 parallel `GET`s never exhaust PostgreSQL's 100 connection slots.

### Verify

```sh
cd python
uv sync --locked
uv run python -m unittest -v test_time_deposit
uv run pytest -q
```

`test_time_deposit.py` pins the calculator contract with literal expected values: eligibility boundaries (`>30`, student `<366`, premium `>45`), unknown and case-mismatched plans, cent rounding with binary floats, ineligible balances still rounded, compounding across calls, in-place mutation with unchanged `id`/`planType`/`days`, empty input, generator input, and no interest leaking between deposits in a batch. `tests/test_api.py` runs against a real PostgreSQL 16 container and covers the seeded listing, commit visibility, read-only listing, an empty database, rollback on failure, absent documentation routes, the two-route set, the exported contract, fractional money handling, the `NUMERIC(18,5)` precision and range constraints, the `409` limit response, and serialization of two overlapping updates with `pg_blocking_pids`.

`uv run pytest` reports branch coverage for the six application modules and fails below 95%. The current suite measures 100% of 199 statements and 24 branches; `uv run coverage report --format=markdown` renders the same table.

### Continuous integration

`.github/workflows/ci.yml` runs on every push to `main`, every pull request, and on demand. The `Tests and coverage` job installs the locked environment with `uv sync --locked`, runs `uv run pytest --cov-report=xml`, writes the markdown coverage table to the job summary, uploads `coverage.xml`, and fails when coverage drops under the configured threshold. The `Compose demo` job builds the stack from scratch, exports the contract, waits for `GET /time-deposits` to answer, then asserts five deposits, a `204` from `POST`, the one-accrual balances `[1201.0, 1203.0, 1205.0, 1200.0, 1200.0]`, and that Swagger serves `/openapi.json`, before tearing the stack down with its volumes.

### Assumptions

- One `POST` applies exactly one monthly accrual to every deposit. It is not idempotent and does not advance `days`.
- Withdrawals are historical records already reflected in the stored balance; the API reports them and never recalculates them.
- Balances are read from PostgreSQL as `Decimal`, converted to `float` only for the legacy calculator, and written back as `Decimal(str(result))`, so the calculator's own rounding is the only rounding applied.
- `NUMERIC(18,5)` stores five fractional places without rescaling them, so a value like `100.004` reaches the calculator unrounded and produces `100.09`.
- The `±1000000000000` bound is a business cap, not an arithmetic limit: it keeps every amount inside the range where a JSON number is exact and gives overflow a defined `409` instead of a database error.
- The connection pool is per process with `min_size=1` and `max_size=10`; scaling out means adding processes, not raising the size against a shared 100-connection server.
- Unknown plan types earn no interest but still receive the calculator's final rounding.
- The update transaction locks the deposit rows with `FOR UPDATE` before calculating, which serializes overlapping updates instead of losing one.

### AI workflow

AI workflow: [festum/ai-rules](https://github.com/festum/ai-rules) + OMP, with Copilot GPT-Sol-6.1 as planner and OpenCode-Go DeepSeek-v4.1Flash as executor.

Setup, the custom rules file, the assistant log, the checks that ran, and the fault-injection results are in [`python/AI_WORKFLOW.md`](python/AI_WORKFLOW.md) and [`python/ai-rules.md`](python/ai-rules.md). The workflow documentation records only executed commands and their observed results.
