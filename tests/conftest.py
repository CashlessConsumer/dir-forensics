"""Shared test fixtures: minimal inventory + case config."""
import json
import os
from pathlib import Path

import pytest


SAMPLE_INVENTORY = {
    "depth": 3,
    "dirs": ["", "engineering/", "engineering/src/", "finance/", "hr/"],
    "files": {
        "README.md": {"name": "README.md", "size": 1024},
        "engineering/app.py": {"name": "app.py", "size": 5000},
        "engineering/src/auth.py": {"name": "auth.py", "size": 3000},
        "engineering/src/config.yaml": {"name": "config.yaml", "size": 800},
        "engineering/src/db_backup.sql": {"name": "db_backup.sql", "size": 50000},
        "finance/report_2024-01-15.xlsx": {"name": "report_2024-01-15.xlsx", "size": 25000},
        "finance/report_2024-02-20.xlsx": {"name": "report_2024-02-20.xlsx", "size": 25000},
        "finance/secret.key": {"name": "secret.key", "size": 2048},
        "finance/cert.pem": {"name": "cert.pem", "size": 4096},
        "finance/Thumbs.db": {"name": "Thumbs.db", "size": 512},
        "hr/employee_data.bak": {"name": "employee_data.bak", "size": 100000},
        "hr/vapt_report.pdf": {"name": "vapt_report.pdf", "size": 20000},
    },
    "stats": {"dirs": 5, "files": 12},
}


@pytest.fixture
def sample_inventory():
    return json.loads(json.dumps(SAMPLE_INVENTORY))


@pytest.fixture
def case_config(tmp_path, sample_inventory):
    from arbor.config import CaseConfig, FlagRule

    inv_path = tmp_path / "inventory.json"
    inv_path.write_text(json.dumps(sample_inventory))

    rules = [
        FlagRule(id="Database", severity="high", color="#60a5fa",
                 extensions=["bak", "db", "sqlite", "mdb"]),
        FlagRule(id="Cert/Key", severity="critical", color="#f87171",
                 extensions=["pem", "key", "crt", "p12", "pfx"]),
        FlagRule(id="SQL", severity="high", color="#c084fc",
                 names=["sql"]),
        FlagRule(id="Config", severity="medium", color="#facc15",
                 names=["config", "credentials", "password"],
                 extensions=["env", "ini", "cfg", "conf", "yaml", "yml"]),
        FlagRule(id="VAPT Report", severity="medium", color="#22c55e",
                 names=["vapt", "vulnerability", "pen test", "pentest"]),
    ]

    out = tmp_path / "output"
    out.mkdir()
    db = tmp_path / "test.duckdb"

    class FakeConfig:
        case = "test-case"
        label = "test.example.org"
        inventory = inv_path
        output_dir = out
        duckdb = db
        flag_rules = rules
        tier0_budget = 50

    return FakeConfig()
