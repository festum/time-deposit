INSERT INTO "timeDeposits" (id, "planType", balance, days) VALUES
    (1, 'basic', 1200, 31),
    (2, 'student', 1200, 365),
    (3, 'premium', 1200, 46),
    (4, 'student', 1200, 366),
    (5, 'premium', 1200, 45);

INSERT INTO withdrawals (id, "timeDepositId", amount, date) VALUES
    (1, 1, 50, '2026-01-15'),
    (2, 1, 25, '2026-01-20'),
    (3, 2, 100, '2026-01-21');

ALTER TABLE "timeDeposits" ALTER COLUMN id RESTART WITH 6;
ALTER TABLE withdrawals ALTER COLUMN id RESTART WITH 4;
