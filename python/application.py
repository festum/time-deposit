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
        with self._uow_factory() as uow:
            deposits = [
                TimeDeposit(deposit.id, deposit.planType, float(deposit.balance), deposit.days)
                for deposit in uow.repository.list_all(for_update=True)
            ]
            self._calculator.update_balance(deposits)
            overflowing = [deposit.id for deposit in deposits if abs(deposit.balance) > MAX_BALANCE]
            if overflowing:
                raise BalanceLimitExceeded(overflowing)
            uow.repository.save_balances(deposits)
