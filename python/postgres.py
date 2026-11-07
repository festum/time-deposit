from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Self

import psycopg

from application import DepositRepository, DepositView, Withdrawal
from time_deposit import TimeDeposit


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
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._context: psycopg.Connection | None = None
        self.repository: DepositRepository

    def __enter__(self) -> Self:
        self._context = psycopg.connect(self._database_url)
        connection = self._context.__enter__()
        self.repository = PostgresDepositRepository(connection)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        assert self._context is not None
        return self._context.__exit__(exc_type, exc_value, traceback)
