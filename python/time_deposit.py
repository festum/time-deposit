from interest_policies import INTEREST_POLICIES


class TimeDeposit:
    def __init__(self, id, planType, balance, days):
        self.id = id
        self.planType = planType
        self.balance = balance
        self.days = days


class TimeDepositCalculator:

    def update_balance(self,xs):
        for td in xs:
            interest = 0
            policy = INTEREST_POLICIES.get(td.planType)
            if policy is not None:
                interest += policy.interest(td)
            td.balance = round(td.balance + ((interest * 100) / 100), 2)
