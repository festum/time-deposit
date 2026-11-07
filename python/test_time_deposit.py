import unittest

from time_deposit import TimeDeposit, TimeDepositCalculator

ELIGIBILITY_TABLE = (
    ('basic', 0, 1200.0),
    ('basic', 30, 1200.0),
    ('basic', 31, 1201.0),
    ('basic', 45, 1201.0),
    ('basic', 46, 1201.0),
    ('basic', 365, 1201.0),
    ('basic', 366, 1201.0),
    ('student', 0, 1200.0),
    ('student', 30, 1200.0),
    ('student', 31, 1203.0),
    ('student', 45, 1203.0),
    ('student', 46, 1203.0),
    ('student', 365, 1203.0),
    ('student', 366, 1200.0),
    ('premium', 0, 1200.0),
    ('premium', 30, 1200.0),
    ('premium', 31, 1200.0),
    ('premium', 45, 1200.0),
    ('premium', 46, 1205.0),
    ('premium', 365, 1205.0),
    ('premium', 366, 1205.0),
    ('unknown', 46, 1200.0),
    ('Basic', 46, 1200.0),
)


class TestTimeDepositCalculator(unittest.TestCase):

    def test_update_balance(self):

        xs = [TimeDeposit(id=1, planType='basic', balance=1234567.0, days=45)]

        calc = TimeDepositCalculator()

        calc.update_balance(xs)
        self.assertEqual(1235595.81, xs[0].balance)

    def test_balances_one_decimal_off(self):
        xs = [TimeDeposit(id=1, planType='basic', balance=100.004, days=45)]

        TimeDepositCalculator().update_balance(xs)

        self.assertEqual(100.09, xs[0].balance)

    def test_plan_and_day_boundaries(self):
        for plan_type, days, expected in ELIGIBILITY_TABLE:
            with self.subTest(planType=plan_type, days=days):
                xs = [TimeDeposit(id=1, planType=plan_type, balance=1200.0, days=days)]

                TimeDepositCalculator().update_balance(xs)

                self.assertEqual(expected, xs[0].balance)

    def test_cent_rounding_is_not_half_up(self):
        cases = (
            ('basic', 150.0, 150.12),
            ('student', 50.0, 50.12),
        )
        for plan_type, balance, expected in cases:
            with self.subTest(planType=plan_type, balance=balance):
                xs = [TimeDeposit(id=1, planType=plan_type, balance=balance, days=31)]

                TimeDepositCalculator().update_balance(xs)

                self.assertEqual(expected, xs[0].balance)

    def test_ineligible_balance_is_still_rounded(self):
        xs = [TimeDeposit(id=1, planType='basic', balance=2.675, days=30)]

        TimeDepositCalculator().update_balance(xs)

        self.assertEqual(2.67, xs[0].balance)

    def test_repeated_calls_compound(self):
        cases = (
            ('basic', 31, 1202.0),
            ('premium', 46, 1210.02),
        )
        for plan_type, days, expected in cases:
            with self.subTest(planType=plan_type, days=days):
                xs = [TimeDeposit(id=1, planType=plan_type, balance=1200.0, days=days)]
                calc = TimeDepositCalculator()

                calc.update_balance(xs)
                calc.update_balance(xs)

                self.assertEqual(expected, xs[0].balance)

    def test_mutates_in_place_and_keeps_identity(self):
        deposit = TimeDeposit(id=7, planType='student', balance=1200.0, days=365)
        xs = [deposit]

        result = TimeDepositCalculator().update_balance(xs)

        self.assertIsNone(result)
        self.assertIs(deposit, xs[0])
        self.assertEqual(7, deposit.id)
        self.assertEqual('student', deposit.planType)
        self.assertEqual(365, deposit.days)
        self.assertEqual(1203.0, deposit.balance)

    def test_empty_input_succeeds(self):
        xs = []

        self.assertIsNone(TimeDepositCalculator().update_balance(xs))
        self.assertEqual([], xs)

    def test_batch_does_not_leak_interest_between_deposits(self):
        expected = [1205.0, 1200.0, 1200.0, 1201.0]
        for clone in (lambda xs: xs, lambda xs: (td for td in xs)):
            with self.subTest(input=clone.__name__):
                xs = [
                    TimeDeposit(id=1, planType='premium', balance=1200.0, days=46),
                    TimeDeposit(id=2, planType='unknown', balance=1200.0, days=46),
                    TimeDeposit(id=3, planType='student', balance=1200.0, days=366),
                    TimeDeposit(id=4, planType='basic', balance=1200.0, days=31),
                ]

                TimeDepositCalculator().update_balance(clone(xs))

                self.assertEqual(expected, [td.balance for td in xs])


if __name__ == '__main__':
    unittest.main()
