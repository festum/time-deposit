# Task rules for the time-deposit take-home

These rules are the custom agent configuration for this repository. Read this file with the agent's read tool before the first tool call of a session, then read `AI_WORKFLOW.md` for the planner/executor setup.

## Preserved contract

- `python/time_deposit.py` exposes `TimeDeposit(id, planType, balance, days)` and `TimeDepositCalculator.update_balance(xs)`. Keep both names, the constructor signature, the attribute names, and the `from time_deposit import ...` import path. Do not add a camelCase alias or optional parameters.
- Keep the arithmetic: annual rates `0.01` (basic), `0.03` (student), `0.05` (premium) divided by 12, eligibility `days > 30` for every plan, `days < 366` for student, `days > 45` for premium, float arithmetic, and the final expression `round(balance + ((interest * 100) / 100), 2)`. Ineligible and unknown plans still get that rounding.

## Behavioral boundaries

- One `update_balance` call applies exactly one monthly accrual per deposit and leaves `days` unchanged.
- Unknown and case-mismatched plan strings earn zero interest.
- A batch must not carry interest between deposits.
- Do not port other language implementations of the calculator.

## API surface

- Expose exactly two operations: `GET /time-deposits` and `POST /time-deposits/update-balances`. No health, create, withdrawal, docs, auth, or CORS routes on the API application.
- Map HTTP to application services, keep PostgreSQL behind the repository and unit-of-work ports, and construct concrete adapters only at the composition boundary.
- `TimeDeposit` stays the calculation model; persistence and withdrawal records stay separate.

## Testing

- Write behavior tests for the calculator before refactoring it, and run them against the unchanged starter first.
- Expected values are independent literals, never produced by the code under test.
- Use testcontainers PostgreSQL for integration tests, never SQLite or a mock database.
- Report only checks that actually ran, with their commands and results.
- `uv run pytest -q` must stay green together with the branch coverage gate in `pyproject.toml` before any change is considered complete. `.github/workflows/ci.yml` enforces the same suite, the same gate, and a Compose smoke test on every push and pull request.

## Handling

- Never push to `ikigai-digital`, create pull requests, or disclose credentials.
- Leave changes uncommitted unless the human asks for a commit.

## Scope

Python-only cutover: the C#, Java, Kotlin, and TypeScript starters are removed and the Python implementation carries the whole solution. Characterize the calculator before changing it, put plan rules behind policies, persist through Psycopg with handwritten SQL and a repository/unit-of-work seam, expose the two operations with an exported OpenAPI document consumed by a separate Swagger UI container, and keep the demo runnable with Docker Compose.
