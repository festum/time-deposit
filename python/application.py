from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Self

from time_deposit import TimeDeposit, TimeDepositCalculator

MAX_BALANCE = Decimal('1000000000000')


@dataclass(frozen=True)
class Withdrawal:
    id: int
    timeDepositId: int
    amount: Decimal
    date: datetime.date


@dataclass(frozen=True)
class DepositView:
    id: int
    planType: str
    balance: Decimal
    days: int
    withdrawals: list[Withdrawal]


class BalanceLimitExceeded(Exception):
    def __init__(self, deposit_ids: Sequence[int]) -> None:
        self.deposit_ids = list(deposit_ids)
        super().__init__(
            f"accrual would move deposits {self.deposit_ids} outside "
            f"the stored range -{MAX_BALANCE}..{MAX_BALANCE}"
        )


class DepositRepository(Protocol):
    # Withdrawal rows are history already reflected in the stored balance. They are reported with
    # the deposit and never subtracted again, because the kata stores the current amount rather
    # than replaying a ledger.
    def list_all(self, *, for_update: bool = False) -> list[DepositView]:
        ...

    def save_balances(self, deposits: Sequence[TimeDeposit]) -> None:
        ...


class DepositUnitOfWork(Protocol):
    repository: DepositRepository

    def __enter__(self) -> Self:
        ...

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        ...


class TimeDepositService:
    def __init__(
        self,
        uow_factory: Callable[[], DepositUnitOfWork],
        calculator: TimeDepositCalculator,
    ) -> None:
        self._uow_factory = uow_factory
        self._calculator = calculator

    def list_deposits(self) -> list[DepositView]:
        with self._uow_factory() as uow:
            return uow.repository.list_all()

    def update_balances(self) -> None:
        # One call is one monthly accrual, and it is deliberately not idempotent: `days` never
        # advances, so the caller decides when a month has passed and every success compounds.
        with self._uow_factory() as uow:
            # NUMERIC(18,5) reaches the calculator as float and comes back through
            # Decimal(str(...)), so storage preserves the input verbatim and the calculator's
            # own round(..., 2) stays the only place a cent boundary is decided.
            deposits = [
                TimeDeposit(deposit.id, deposit.planType, float(deposit.balance), deposit.days)
                for deposit in uow.repository.list_all(for_update=True)
            ]
            self._calculator.update_balance(deposits)
            overflowing = [deposit.id for deposit in deposits if abs(deposit.balance) > MAX_BALANCE]
            if overflowing:
                raise BalanceLimitExceeded(overflowing)
            uow.repository.save_balances(deposits)
