from __future__ import annotations

import threading
from collections.abc import Sequence
from decimal import Decimal
from typing import Self

import psycopg
from psycopg_pool import ConnectionPool

from application import DepositRepository, DepositView, Withdrawal
from time_deposit import TimeDeposit

POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 10


class ConnectionPools:
    """One process-wide pool per database URL, opened on first use."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pools: dict[str, ConnectionPool] = {}

    def get(self, database_url: str) -> ConnectionPool:
        with self._lock:
            pool = self._pools.get(database_url)
            if pool is None:
                pool = ConnectionPool(
                    database_url,
                    min_size=POOL_MIN_SIZE,
                    max_size=POOL_MAX_SIZE,
                    open=False,
                    name=f'time-deposit-{len(self._pools)}',
                )
                pool.open()
                self._pools[database_url] = pool
            return pool

    def close_all(self) -> None:
        with self._lock:
            pools = list(self._pools.values())
            self._pools.clear()
        for pool in pools:
            pool.close()


POOLS = ConnectionPools()


class PostgresDepositRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def list_all(self, *, for_update: bool = False) -> list[DepositView]:
        if for_update:
            self._connection.execute('SELECT id FROM "timeDeposits" ORDER BY id FOR UPDATE').fetchall()
        rows = self._connection.execute(
            """
            SELECT d.id, d."planType", d.balance, d.days,
                   w.id AS withdrawal_id, w."timeDepositId", w.amount, w.date
            FROM "timeDeposits" AS d
            LEFT JOIN withdrawals AS w ON w."timeDepositId" = d.id
            ORDER BY d.id, w.date, w.id
            """
        ).fetchall()

        deposits: list[DepositView] = []
        index_by_id: dict[int, int] = {}
        for row in rows:
            deposit_id = row[0]
            position = index_by_id.get(deposit_id)
            if position is None:
                position = len(deposits)
                index_by_id[deposit_id] = position
                deposits.append(
                    DepositView(
                        id=deposit_id,
                        planType=row[1],
                        balance=row[2],
                        days=row[3],
                        withdrawals=[],
                    )
                )
            if row[4] is not None:
                deposits[position].withdrawals.append(
                    Withdrawal(id=row[4], timeDepositId=row[5], amount=row[6], date=row[7])
                )
        return deposits

    def save_balances(self, deposits: Sequence[TimeDeposit]) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                'UPDATE "timeDeposits" SET balance = %s WHERE id = %s',
                [(Decimal(str(deposit.balance)), deposit.id) for deposit in deposits],
            )


class PostgresUnitOfWork:
    def __init__(self, database_url: str, pools: ConnectionPools | None = None) -> None:
        self._database_url = database_url
        self._pools = pools if pools is not None else POOLS
        self._context = None
        self._connection: psycopg.Connection | None = None
        self.repository: DepositRepository

    def __enter__(self) -> Self:
        self._context = self._pools.get(self._database_url).connection()
        self._connection = self._context.__enter__()
        self.repository = PostgresDepositRepository(self._connection)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        assert self._context is not None
        return self._context.__exit__(exc_type, exc_value, traceback)
