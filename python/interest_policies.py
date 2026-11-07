from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from time_deposit import TimeDeposit


class InterestPolicy(Protocol):
    def interest(self, deposit: TimeDeposit) -> float:
        ...


@dataclass(frozen=True)
class MonthlyInterestPolicy:
    annual_rate: float
    min_days_exclusive: int
    max_days_exclusive: int | None = None

    def interest(self, deposit: TimeDeposit) -> float:
        if deposit.days <= self.min_days_exclusive:
            return 0
        if self.max_days_exclusive is not None and deposit.days >= self.max_days_exclusive:
            return 0
        return (deposit.balance * self.annual_rate) / 12


INTEREST_POLICIES: dict[str, InterestPolicy] = {
    'basic': MonthlyInterestPolicy(0.01, 30),
    'student': MonthlyInterestPolicy(0.03, 30, 366),
    'premium': MonthlyInterestPolicy(0.05, 45),
}
