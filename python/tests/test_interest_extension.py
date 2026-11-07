from __future__ import annotations

import unittest

from interest_policies import INTEREST_POLICIES
from time_deposit import TimeDeposit, TimeDepositCalculator


class TieredPolicy:
    def interest(self, deposit: TimeDeposit) -> float:
        if deposit.days <= 30:
            return 0
        tiers = [(min(deposit.balance, 1000.0), 0.01), (max(deposit.balance - 1000.0, 0.0), 0.02)]
        return sum(amount * rate / 12 for amount, rate in tiers)


class TestInterestExtension(unittest.TestCase):

    def setUp(self):
        INTEREST_POLICIES['tiered-test'] = TieredPolicy()

    def tearDown(self):
        del INTEREST_POLICIES['tiered-test']

    def test_registered_policy_runs_through_existing_dispatch(self):
        cases = (
            (600.0, 600.5),
            (1600.0, 1601.83),
        )
        for balance, expected in cases:
            with self.subTest(balance=balance):
                deposit = TimeDeposit(id=1, planType='tiered-test', balance=balance, days=31)

                TimeDepositCalculator().update_balance([deposit])

                self.assertEqual(expected, deposit.balance)
                self.assertEqual(1, deposit.id)
                self.assertEqual('tiered-test', deposit.planType)
                self.assertEqual(31, deposit.days)


if __name__ == '__main__':
    unittest.main()
