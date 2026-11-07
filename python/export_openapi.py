from __future__ import annotations

import json
import os
from pathlib import Path

from api import create_app
from application import TimeDepositService
from postgres import PostgresUnitOfWork
from time_deposit import TimeDepositCalculator


def main(target: Path | None = None) -> None:
    service = TimeDepositService(
        lambda: PostgresUnitOfWork("postgresql://unused"),
        TimeDepositCalculator(),
    )
    app = create_app(service)
    schema = app.openapi()
    schema["servers"] = [{"url": os.environ.get("API_BASE_URL", "http://localhost:8080")}]
    destination = target or Path(__file__).with_name("openapi.json")
    destination.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
