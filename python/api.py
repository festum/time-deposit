from __future__ import annotations

import datetime
import os
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from application import BalanceLimitExceeded, DepositView, TimeDepositService
from postgres import PostgresUnitOfWork
from time_deposit import TimeDepositCalculator

BALANCE_LIMIT = '1000000000000'


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


class BalanceLimitResponse(BaseModel):
    detail: Literal['balance limit exceeded']
    message: str
    depositIds: list[int]


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

    @app.exception_handler(BalanceLimitExceeded)
    def balance_limit_exceeded(request: Request, error: BalanceLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=BalanceLimitResponse(
                detail='balance limit exceeded',
                message=str(error),
                depositIds=error.deposit_ids,
            ).model_dump(),
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
        response_class=Response,
        summary="Apply one monthly interest accrual to every deposit",
        description=(
            "Applies exactly one monthly accrual to every stored deposit, in a single transaction "
            "that locks the deposit rows. Interest is monthly: basic 1%, student 3% while under 366 "
            "days, premium 5% after 45 days; no interest applies within the first 30 days, and an "
            "unknown plan type earns none. Deposit `days` never changes and withdrawal rows are not "
            "touched. The call is not idempotent: each success adds another accrual permanently. "
            f"Balances are stored as NUMERIC(18,5) bounded to ±{BALANCE_LIMIT}; if the accrual would "
            "move any deposit outside that range the whole batch is rejected with 409 and nothing is "
            "written. Responds with an empty body."
        ),
        responses={
            409: {
                'model': BalanceLimitResponse,
                'description': (
                    "The accrual would move at least one balance outside the stored range "
                    f"±{BALANCE_LIMIT}. The transaction rolls back, so no deposit changes."
                ),
            },
        },
    )
    def update_time_deposit_balances():
        service.update_balances()

    return app
