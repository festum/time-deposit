from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

import export_openapi
import postgres
from api import create_app
from application import TimeDepositService
from postgres import PostgresDepositRepository, PostgresUnitOfWork
from time_deposit import TimeDepositCalculator

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = PYTHON_ROOT / 'sql' / '001_init.sql'
OPENAPI_JSON = PYTHON_ROOT / 'openapi.json'

FIXTURE_DEPOSITS = [
    (1, 'basic', Decimal('1200'), 31),
    (2, 'student', Decimal('1200'), 365),
    (3, 'premium', Decimal('1200'), 46),
    (4, 'student', Decimal('1200'), 366),
    (5, 'premium', Decimal('1200'), 45),
]
FIXTURE_WITHDRAWALS = [
    (1, 1, Decimal('50'), '2026-01-15'),
    (2, 1, Decimal('25'), '2026-01-20'),
    (3, 2, Decimal('100'), '2026-01-21'),
]
BALANCES_AFTER_ONE_ACCRUAL = [1201.0, 1203.0, 1205.0, 1200.0, 1200.0]
BALANCES_AFTER_TWO_ACCRUALS = [1202.0, 1206.01, 1210.02, 1200.0, 1200.0]

DEPOSIT_KEYS = {'id', 'planType', 'balance', 'days', 'withdrawals'}
WITHDRAWAL_KEYS = {'id', 'timeDepositId', 'amount', 'date'}


@pytest.fixture(scope='session')
def postgres_container():
    with PostgresContainer('postgres:16', driver=None) as container:
        yield container


@pytest.fixture(scope='session')
def database_url(postgres_container):
    url = postgres_container.get_connection_url()
    with psycopg.connect(url) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding='utf-8'))
        conn.commit()
    return url


@pytest.fixture()
def connection(database_url):
    conn = psycopg.connect(database_url)
    yield conn
    conn.close()


@pytest.fixture()
def seeded(connection):
    reset(connection)
    insert(connection, FIXTURE_DEPOSITS, FIXTURE_WITHDRAWALS)
    return connection


@pytest.fixture()
def service(database_url):
    return TimeDepositService(lambda: PostgresUnitOfWork(database_url), TimeDepositCalculator())


@pytest.fixture()
def client(service):
    with TestClient(create_app(service)) as test_client:
        yield test_client


def reset(conn) -> None:
    conn.execute('TRUNCATE TABLE withdrawals, "timeDeposits" RESTART IDENTITY CASCADE')
    conn.commit()


def insert(conn, deposits, withdrawals=()) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            'INSERT INTO "timeDeposits" (id, "planType", balance, days) VALUES (%s, %s, %s, %s)',
            deposits,
        )
        cursor.executemany(
            'INSERT INTO withdrawals (id, "timeDepositId", amount, date) VALUES (%s, %s, %s, %s)',
            withdrawals,
        )
    conn.commit()


def stored_rows(conn):
    deposits = conn.execute(
        'SELECT id, "planType", balance, days FROM "timeDeposits" ORDER BY id'
    ).fetchall()
    withdrawals = conn.execute(
        'SELECT id, "timeDepositId", amount, date FROM withdrawals ORDER BY id'
    ).fetchall()
    return deposits, withdrawals


def assert_json_number(value) -> None:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)


def test_connection_is_postgresql(connection):
    assert 'PostgreSQL' in connection.execute('SELECT version()').fetchone()[0]


def test_schema_contract(connection):
    rows = connection.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_name IN ('timeDeposits', 'withdrawals')
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    assert rows == [
        ('timeDeposits', 'id', 'integer'),
        ('timeDeposits', 'planType', 'text'),
        ('timeDeposits', 'days', 'integer'),
        ('timeDeposits', 'balance', 'numeric'),
        ('withdrawals', 'id', 'integer'),
        ('withdrawals', 'timeDepositId', 'integer'),
        ('withdrawals', 'amount', 'numeric'),
        ('withdrawals', 'date', 'date'),
    ]

    foreign_key = connection.execute(
        """
        SELECT kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = 'withdrawals'
        """
    ).fetchall()
    assert foreign_key == [('timeDepositId', 'timeDeposits', 'id')]


def test_list_returns_seeded_deposits(seeded, client):
    response = client.get('/time-deposits')

    assert response.status_code == 200
    payload = response.json()
    assert [entry['id'] for entry in payload] == [1, 2, 3, 4, 5]
    assert [entry['planType'] for entry in payload] == ['basic', 'student', 'premium', 'student', 'premium']
    assert [entry['balance'] for entry in payload] == [1200.0, 1200.0, 1200.0, 1200.0, 1200.0]
    assert [entry['days'] for entry in payload] == [31, 365, 46, 366, 45]
    for entry in payload:
        assert set(entry) == DEPOSIT_KEYS
        assert_json_number(entry['balance'])

    assert payload[0]['withdrawals'] == [
        {'id': 1, 'timeDepositId': 1, 'amount': 50.0, 'date': '2026-01-15'},
        {'id': 2, 'timeDepositId': 1, 'amount': 25.0, 'date': '2026-01-20'},
    ]
    assert [withdrawal['id'] for withdrawal in payload[1]['withdrawals']] == [3]
    assert [entry['withdrawals'] for entry in payload[2:]] == [[], [], []]
    for entry in payload:
        for withdrawal in entry['withdrawals']:
            assert set(withdrawal) == WITHDRAWAL_KEYS
            assert_json_number(withdrawal['amount'])
            assert_json_number(withdrawal['id'])


def test_update_applies_one_accrual_and_commits(seeded, client, database_url):
    response = client.post('/time-deposits/update-balances')

    assert response.status_code == 204
    assert response.content == b''

    payload = client.get('/time-deposits').json()
    assert [entry['balance'] for entry in payload] == BALANCES_AFTER_ONE_ACCRUAL
    assert [entry['days'] for entry in payload] == [31, 365, 46, 366, 45]
    assert payload[0]['withdrawals'] == [
        {'id': 1, 'timeDepositId': 1, 'amount': 50.0, 'date': '2026-01-15'},
        {'id': 2, 'timeDepositId': 1, 'amount': 25.0, 'date': '2026-01-20'},
    ]

    with psycopg.connect(database_url) as independent:
        balances = independent.execute('SELECT balance FROM "timeDeposits" ORDER BY id').fetchall()
    assert [row[0] for row in balances] == [Decimal('1201'), Decimal('1203'), Decimal('1205'), Decimal('1200'), Decimal('1200')]


def test_listing_does_not_write(seeded, client, database_url):
    before = stored_rows(seeded)

    for _ in range(3):
        assert client.get('/time-deposits').status_code == 200

    with psycopg.connect(database_url) as independent:
        assert stored_rows(independent) == before


def test_default_wiring_reads_database_url(seeded, database_url, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', database_url)

    with TestClient(create_app()) as client:
        response = client.get('/time-deposits')

    assert response.status_code == 200
    assert [entry['id'] for entry in response.json()] == [1, 2, 3, 4, 5]


def test_openapi_export_reproduces_the_committed_contract(tmp_path):
    target = tmp_path / 'openapi.json'

    export_openapi.main(target)

    assert target.read_text(encoding='utf-8') == OPENAPI_JSON.read_text(encoding='utf-8')


def test_empty_database(database_url):
    with psycopg.connect(database_url) as conn:
        reset(conn)
    service = TimeDepositService(lambda: PostgresUnitOfWork(database_url), TimeDepositCalculator())

    with TestClient(create_app(service)) as client:
        listing = client.get('/time-deposits')
        update = client.post('/time-deposits/update-balances')

    assert listing.status_code == 200
    assert listing.json() == []
    assert update.status_code == 204
    assert update.content == b''
    with psycopg.connect(database_url) as conn:
        assert conn.execute('SELECT count(*) FROM "timeDeposits"').fetchone()[0] == 0


def test_failed_save_rolls_back(seeded, database_url, monkeypatch):
    before = stored_rows(seeded)

    def failing_save(self: PostgresDepositRepository, deposits) -> None:
        first = deposits[0]
        self._connection.execute(
            'UPDATE "timeDeposits" SET balance = %s WHERE id = %s',
            (Decimal(str(first.balance)), first.id),
        )
        raise RuntimeError('forced save failure')

    monkeypatch.setattr(PostgresDepositRepository, 'save_balances', failing_save)
    service = TimeDepositService(lambda: PostgresUnitOfWork(database_url), TimeDepositCalculator())

    with TestClient(create_app(service), raise_server_exceptions=False) as client:
        assert client.post('/time-deposits/update-balances').status_code == 500

    with psycopg.connect(database_url) as independent:
        assert stored_rows(independent) == before


def test_documentation_routes_are_absent(client):
    for path in ('/docs', '/redoc', '/openapi.json'):
        assert client.get(path).status_code == 404


def test_exactly_two_registered_operations(service):
    app = create_app(service)
    operations = {
        (route.path, method)
        for route in app.routes
        if hasattr(route, 'methods')
        for method in route.methods
    }

    assert operations == {('/time-deposits', 'GET'), ('/time-deposits/update-balances', 'POST')}


def test_openapi_matches_exported_contract(service):
    exported = json.loads(OPENAPI_JSON.read_text(encoding='utf-8'))
    generated = create_app(service).openapi()
    generated['servers'] = [{'url': 'http://localhost:8080'}]

    assert exported == generated
    assert set(exported['paths']) == {'/time-deposits', '/time-deposits/update-balances'}
    assert set(exported['paths']['/time-deposits']) == {'get'}
    assert set(exported['paths']['/time-deposits/update-balances']) == {'post'}

    deposit_schema = exported['components']['schemas']['DepositResponse']
    assert set(deposit_schema['required']) == DEPOSIT_KEYS
    assert deposit_schema['properties']['balance']['type'] == 'number'
    assert deposit_schema['properties']['days']['type'] == 'integer'
    withdrawal_schema = exported['components']['schemas']['WithdrawalResponse']
    assert set(withdrawal_schema['required']) == WITHDRAWAL_KEYS
    assert withdrawal_schema['properties']['amount']['type'] == 'number'
    assert withdrawal_schema['properties']['date']['format'] == 'date'

    post_operation = exported['paths']['/time-deposits/update-balances']['post']
    assert 'requestBody' not in post_operation
    assert 'content' not in post_operation['responses']['204']


def test_fractional_balances_round_at_the_calculator_boundary(database_url, connection):
    reset(connection)
    insert(
        connection,
        [(1, 'basic', Decimal('100.004'), 45), (2, 'basic', Decimal('2.675'), 30)],
        [(1, 1, Decimal('25.125'), '2026-02-01')],
    )
    connection.commit()
    service = TimeDepositService(lambda: PostgresUnitOfWork(database_url), TimeDepositCalculator())

    with TestClient(create_app(service)) as client:
        before = client.get('/time-deposits').json()
        assert [entry['balance'] for entry in before] == [100.004, 2.675]
        assert before[0]['withdrawals'][0]['amount'] == 25.125
        stored_before = connection.execute(
            'SELECT balance FROM "timeDeposits" ORDER BY id'
        ).fetchall()
        assert [row[0] for row in stored_before] == [Decimal('100.004'), Decimal('2.675')]

        assert client.post('/time-deposits/update-balances').status_code == 204
        after = client.get('/time-deposits').json()

    assert [entry['balance'] for entry in after] == [100.09, 2.67]
    assert after[0]['withdrawals'][0]['amount'] == 25.125
    with psycopg.connect(database_url) as independent:
        balances = independent.execute('SELECT balance FROM "timeDeposits" ORDER BY id').fetchall()
        amounts = independent.execute('SELECT amount FROM withdrawals').fetchall()
    assert [row[0] for row in balances] == [Decimal('100.09'), Decimal('2.67')]
    assert [row[0] for row in amounts] == [Decimal('25.125')]


class PidUnitOfWork(PostgresUnitOfWork):
    pid: int

    def __enter__(self):
        super().__enter__()
        self.pid = self._context.execute('SELECT pg_backend_pid()').fetchone()[0]
        return self


class PausingCalculator(TimeDepositCalculator):
    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self._entered = entered
        self._release = release

    def update_balance(self, xs) -> None:
        self._entered.set()
        assert self._release.wait(timeout=30)
        super().update_balance(xs)


class RecordingCalculator(TimeDepositCalculator):
    def __init__(self) -> None:
        self.called = threading.Event()

    def update_balance(self, xs) -> None:
        self.called.set()
        super().update_balance(xs)


def test_concurrent_updates_serialize(seeded, database_url):
    entered = threading.Event()
    release = threading.Event()
    first_uows: list[PidUnitOfWork] = []
    second_uows: list[PidUnitOfWork] = []

    def first_factory() -> PidUnitOfWork:
        uow = PidUnitOfWork(database_url)
        first_uows.append(uow)
        return uow

    def second_factory() -> PidUnitOfWork:
        uow = PidUnitOfWork(database_url)
        second_uows.append(uow)
        return uow

    first_service = TimeDepositService(first_factory, PausingCalculator(entered, release))
    second_calculator = RecordingCalculator()
    second_service = TimeDepositService(second_factory, second_calculator)

    statuses: dict[str, int] = {}
    failures: list[BaseException] = []

    def post(name: str, service: TimeDepositService) -> None:
        try:
            with TestClient(create_app(service)) as client:
                statuses[name] = client.post('/time-deposits/update-balances').status_code
        except BaseException as error:  # noqa: BLE001 - surfaced by the assertions below
            failures.append(error)

    first_worker = threading.Thread(target=post, args=('first', first_service), daemon=True)
    second_worker = threading.Thread(target=post, args=('second', second_service), daemon=True)

    blocker_observed = False
    blocked_second_pid = None
    try:
        first_worker.start()
        assert entered.wait(timeout=30), 'first update never reached the calculator'
        first_pid = first_uows[0].pid

        second_worker.start()
        deadline = time.monotonic() + 30
        with psycopg.connect(database_url, autocommit=True) as observer:
            while time.monotonic() < deadline:
                if second_uows and getattr(second_uows[0], 'pid', None) is not None:
                    second_pid = second_uows[0].pid
                    blockers = observer.execute(
                        'SELECT pg_blocking_pids(%s)', (second_pid,)
                    ).fetchone()[0]
                    if first_pid in blockers:
                        blocker_observed = True
                        blocked_second_pid = second_pid
                        break
                if second_calculator.called.is_set():
                    break
                time.sleep(0.05)

        assert not second_calculator.called.is_set(), 'second update entered the calculator before the first released'
        assert blocker_observed, 'second update was never blocked by the first transaction'
    finally:
        release.set()
        first_worker.join(timeout=60)
        second_worker.join(timeout=60)

    assert failures == []
    assert statuses == {'first': 204, 'second': 204}
    assert blocked_second_pid is not None
    with psycopg.connect(database_url) as independent:
        balances = independent.execute('SELECT balance FROM "timeDeposits" ORDER BY id').fetchall()
    assert [row[0] for row in balances] == [
        Decimal('1202'), Decimal('1206.01'), Decimal('1210.02'), Decimal('1200'), Decimal('1200')
    ]
