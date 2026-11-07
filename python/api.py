from __future__ import annotations

import datetime
import os

from fastapi import FastAPI
from pydantic import BaseModel

from application import DepositView, TimeDepositService
from postgres import PostgresUnitOfWork
from time_deposit import TimeDepositCalculator


class WithdrawalResponse(BaseModel):
    id: int
    timeDepositId: int
    amount: float
    date: datetime.date


class DepositResponse(BaseModel):
    id: int
    planType: str
    balance: float
    days: int
    withdrawals: list[WithdrawalResponse]


def _to_response(deposit: DepositView) -> DepositResponse:
    return DepositResponse(
        id=deposit.id,
        planType=deposit.planType,
        balance=float(deposit.balance),
        days=deposit.days,
        withdrawals=[
            WithdrawalResponse(
                id=withdrawal.id,
                timeDepositId=withdrawal.timeDepositId,
                amount=float(withdrawal.amount),
                date=withdrawal.date,
            )
            for withdrawal in deposit.withdrawals
        ],
    )


def create_app(service: TimeDepositService | None = None) -> FastAPI:
    if service is None:
        database_url = os.environ['DATABASE_URL']
        service = TimeDepositService(
            lambda: PostgresUnitOfWork(database_url),
            TimeDepositCalculator(),
        )

    app = FastAPI(
        title="Time Deposit API",
        version="1.0.0",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        redirect_slashes=False,
    )

    @app.get(
        "/time-deposits",
        operation_id="listTimeDeposits",
        response_model=list[DepositResponse],
        status_code=200,
        summary="List all time deposits",
        description=(
            "Returns every stored time deposit with its plan type, current balance, days, and "
            "withdrawal history. Balances and withdrawal amounts are JSON numbers; dates are ISO "
            "`YYYY-MM-DD`. Deposit `days` stays as stored; withdrawals are historical records "
            "already reflected in the stored balance. An empty database returns an empty array."
        ),
    )
    def list_time_deposits():
        return [_to_response(deposit) for deposit in service.list_deposits()]

    @app.post(
        "/time-deposits/update-balances",
        operation_id="updateTimeDepositBalances",
        status_code=204,
        summary="Apply one monthly interest accrual to every deposit",
        description=(
            "Applies exactly one monthly accrual to every stored deposit, in a single transaction "
            "that locks the deposit rows. Interest is monthly: basic 1%, student 3% while under 366 "
            "days, premium 5% after 45 days; no interest applies within the first 30 days, and an "
            "unknown plan type earns none. Deposit `days` never changes and withdrawal rows are not "
            "touched. The call is not idempotent: each success adds another accrual permanently. "
            "Responds with an empty body."
        ),
    )
    def update_time_deposit_balances():
        service.update_balances()

    return app
