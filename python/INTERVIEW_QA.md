# Walkthrough notes

Behaviour boundaries, test layering, and the questions this submission has to answer out loud. Every number here was measured on this tree; nothing is estimated.

## What the brief fixed and what it left open

|Item|Status|Evidence|
|---|---|---|
|`TimeDeposit(id, planType, balance, days)` and the attribute names|Frozen, byte-identical to the starter|`git diff c4ea358:python/time_deposit.py python/time_deposit.py` shows only the dispatch lines and the added import|
|`update_balance(self,xs)` signature, including the missing space after the comma|Frozen|Same diff: the `def` line is unreachable by the patch|
|`round(td.balance + ((interest * 100) / 100), 2)`|Frozen|Same diff: last line of the loop unchanged|
|Annual rates `0.01` / `0.03` / `0.05` divided by 12|Frozen|`python/interest_policies.py`|
|The body of `update_balance`|Open: §4 asks for extensibility, and the `if/elif` chain was the only extension point|`python/interest_policies.py` + `python/tests/test_interest_extension.py`|
|Everything else: persistence, HTTP, contract, tests|Open|`README.md` §Layout|

## Behaviour boundaries

Each row has a test that fails if the boundary moves.

|Boundary|Rule|Pinned by|
|---|---|---|
|No interest for anyone|`days > 30`; `days == 30` earns nothing|`ELIGIBILITY_TABLE` rows `('basic', 30, 1200.0)` and `('basic', 31, 1201.0)`|
|Student stops at one year|interest while `days < 366`; `days == 366` earns nothing|`('student', 365, 1203.0)` and `('student', 366, 1200.0)`|
|Premium starts late|interest while `days > 45`; `days == 45` earns nothing|`('premium', 45, 1200.0)` and `('premium', 46, 1205.0)`|
|Unknown plan|no interest, still rounded by the frozen expression|`('unknown', 46, 1200.0)`|
|Case-sensitive plan|`'Basic'` is unknown|`('Basic', 46, 1200.0)`|
|Zero and negative balances|accrue and round like any other; `-1200` posts `-1201`|`test_zero_and_negative_balances_accrue`|
|`days` and `id`/`planType`|never change|every `ELIGIBILITY_TABLE` row asserts all three; the API test asserts stored `days` `[31, 365, 46, 366, 45]` after a `POST`|
|Withdrawals|history, already reflected in the balance, never subtracted again|`test_list_returns_seeded_deposits`, `test_listing_does_not_write`|
|Withdrawal order|`date`, then `id`|`test_withdrawals_are_ordered_by_date_then_id`|
|One call, one accrual|not idempotent, `days` never advances|`test_update_applies_one_accrual_and_commits`, `BALANCES_AFTER_TWO_ACCRUALS`|
|Empty database|`GET` → `[]`, `POST` → `204` no-op|`test_empty_database`|
|Stored range|`±1000000000000`, checked in the service so the unit of work rolls back|`test_accrual_beyond_the_stored_range_conflicts_without_writing`|
|Overflow answer|`409` with `depositIds`, no rows written|same test|
|Failed save|transaction rolls back|`test_failed_save_rolls_back`|
|Exactly two routes|no `/docs`, `/redoc`, `/openapi.json` on the app|`test_exactly_two_registered_operations`, `test_documentation_routes_are_absent`|
|`204` shape|empty body and no `content-type`|`test_update_applies_one_accrual_and_commits`|
|Fractional storage|`100.004` reaches the calculator unrounded and posts `100.09`|`test_fractional_balances_round_at_the_calculator_boundary`|

## How the tests are layered

|Layer|File|Shape|
|---|---|---|
|Calculator contract, no I/O|`python/test_time_deposit.py`|9 `unittest` methods; the eligibility table is 23 literal rows; in-place mutation, empty input, generator input, batch isolation, compounding|
|Extension seam|`python/tests/test_interest_extension.py`|1 method, 2 subtests: a test-only `tiered-test` policy registered into `INTEREST_POLICIES` and run through the public calculator (`600.5`, `1601.83`)|
|Adapters and contract|`python/tests/test_api.py`|20 test functions, 2 parametrized; 19 of the 20 use a Testcontainers PostgreSQL 16 container|

Measured: 37 tests plus 31 subtests pass; 199 statements, 24 branches, 100% coverage, `fail_under = 95` in `pyproject.toml`.

## How to run them

```sh
cd python
uv sync --locked
uv run python -m unittest -v test_time_deposit    # calculator contract, seconds, no Docker
uv run pytest -q                                  # everything; Docker required for Testcontainers
uv run export_openapi.py                          # regenerate openapi.json after any contract change
```

## How the suite is proven sensitive

Coverage says what ran, not what would break. Each variant was applied alone, the suite rerun, and the code restored:

|Variant|Failure observed|
|---|---|
|`basic` minimum `>30` to `>29`|`1200.0 != 1201.0`, and the ineligible rounding case `2.67 != 2.68`|
|`student` maximum `<366` to `<367`|`1200.0 != 1203.0`, plus a batch mismatch on the seeded five|
|`premium` minimum `>45` to `>44`|`1200.0 != 1205.0`|
|Round the interest before adding it|`100.09 != 100.08`|
|Skip the final rounding for zero interest|`2.67 != 2.675`|
|`ORDER BY d.id, w.date, w.id` to `ORDER BY d.id, w.id`|`assert [10, 11, 20, 21] == [11, 20, 21, 10]`|
|Drop `response_class=Response` from the `POST`|`AssertionError: Headers({'content-type': 'application/json'})`|

The last two were added after the first five were recorded, which is the point: a mutation that survives means an oracle is missing, not that the code is right.

## Numbers to quote

|Claim|Value|
|---|---|
|Equivalence sweep, single call|4,181,892 cases (12 plan strings × 2,437 balances × 143 day counts), 0 mismatches against `git show c4ea358:python/time_deposit.py`|
|Equivalence sweep, compounding|806,400 calls (12 plans × 400 balances × 7 day counts × 24 rounds), 0 mismatches|
|Float vs exact decimal, balances 1..3000|120 `basic`, 360 `student`, 104 `premium` diverge by one cent|
|Worked examples|`basic` 42 → `42.03` (exact `42.04`); `student` 6 → `6.01` (exact `6.02`); `premium` 6 → `6.03` (exact `6.02`)|
|Concurrent `POST` serialization|second backend blocked by the first's transaction; final balances `1202 / 1206.01 / 1210.02`|
|`GET` 1,000 rows / `POST`|12 ms / 42 ms; 205,000 rows: 2.77 s / 7.73 s|
|200 parallel `GET`, 5 rows|372 req/s, 11 backends, `min_size=1`, `max_size=10`|

The three "worked examples" and the 120/360/104 counts were re-derived with exact rational arithmetic, not float arithmetic, so they do not depend on the very thing they describe.

## Questions to expect

**Why touch the calculator at all?**
The constraint freezes the signature and the shared class. The guideline says behaviour must remain unchanged after refactoring, and §4 requires extensibility. The `if/elif` chain was the only extension point, so the body had to move. Signature, class, and the final rounding expression are byte-identical; the dispatch is a registry lookup; equivalence is proven over 4.98 million calls.

**Why a registry instead of three subclasses?**
The plans differ in three numbers: annual rate, lower day bound, optional upper day bound. One frozen dataclass parameterized three ways is less code than three classes, and it keeps a single rounding site. A new plan registers an object with the same `interest(deposit)` method; the extension test proves that path with a tiered policy.

**Why float rather than Decimal everywhere?**
The calculator is frozen and its arithmetic is float. Storage is `NUMERIC(18,5)`, the ISO 20022 `ActiveCurrencyAndAmount` shape: 18 total digits, 5 fraction digits. The path is `NUMERIC` → `Decimal` → `float` for the calculator → `Decimal(str(result))` on writeback, so storage preserves the input verbatim and the calculator's own `round(..., 2)` stays the only place a cent boundary is decided. The divergence from exact decimal is measured, stated in the README, and is a property of the arithmetic the task fixed, not of the storage.

**Why 409 rather than 400 or 500?**
The request is well-formed and the server is healthy; the accrual conflicts with current resource state. A range `CHECK` violation would surface as a database error and read as a server fault, so the guard lives in the service before the save, and the unit of work rolls back the whole batch.

**Is `POST` idempotent?**
Deliberately not. One call is one monthly accrual and `days` never advances, so the caller decides when a month has passed. Retry safety would need an idempotency key on the request, which the brief does not ask for.

**Why lock ids before the joined read?**
`SELECT ... FOR UPDATE` over the join locks withdrawal rows too and leaves the ordering of two concurrent batches to chance. Pre-selecting `id ... ORDER BY id FOR UPDATE` in the same transaction serializes overlapping accruals. The test proves it with `pg_blocking_pids`, not by hoping.

**Why `NUMERIC(18,5)` and a ±1e12 cap?**
Five fraction places so fractional inputs reach the calculator unrounded; the cap keeps every stored amount inside the range where a JSON number is exact and gives overflow a defined `409`.

**Why no ORM and no pagination?**
Two tables and handwritten parameterized SQL keep the repository port honest: no `Session` or lazy loading leaks into the application layer. Pagination is a deliberate boundary, recorded with its upgrade path in the README's scaling table.

**Why did a wrong `204` survive the suite?**
The test asserted the status code and the empty body, and Starlette's default `JSONResponse` sets `content-type: application/json` even when there is nothing to serialize. The CI smoke job was equally blind: it checks `%{http_code}` and never the headers. `curl -i` against the running stack is what showed the header, which is the argument for exercising the real edge rather than only the in-process client. The route now declares `response_class=Response` and the test asserts `'content-type' not in response.headers`; on the live stack the reply is a bare `204` with `date` and `server` only, through the API port and through the Swagger proxy alike.

**What would you change?**
Three things. The equivalence sweep is a one-off script, so a reader cannot re-run it without rebuilding it; it belongs in the suite as a committed property test. The divergence counts from exact decimal are measured and then recorded in the README as expected behaviour, but nothing fails if a future change moves them. And the smoke job should assert response headers, not just status codes, because that is exactly the gap that let the `content-type` defect through.

**What is not verified?**
Every claim in this document names the command or file that produces it, and `uv run pytest -q` reproduces the coverage numbers. What no committed check enforces: the equivalence sweep, the divergence counts, and the load and concurrency figures in the README, which come from one-off drivers against the Compose stack. Those numbers are as measured, not as continuously asserted.
