"""Synthetic inventory generator for the demo case.

Produces a realistic directory tree with ~3,000 files across ~400 dirs,
including intentional duplicates, security-flaggable names, and multiple
file extensions. All data is fictional — no real files, no PII.

Output conforms to the canonical inventory contract:
    {"depth": N, "dirs": [...], "files": {relpath: {name, url, size}}, "stats": {...}}
"""

from __future__ import annotations

import hashlib
import random
import time

random.seed(42)

# ── Fictional org structure ──────────────────────────────────────────

DEPARTMENTS = ["Engineering", "Finance", "HR", "Legal", "Operations", "Sales", "IT-Infra"]
REGIONS = ["North", "South", "East", "West", "Central"]
YEARS = ["2023", "2024", "2025"]

FILE_TEMPLATES = {
    "pdf": ["Audit_Report", "Compliance_Doc", "Contract", "Invoice", "Policy", "Q{q}_Review"],
    "xlsx": ["Budget_v{n}", "Payroll_{month}", "Forecast_{year}", "Expense_Report", "Vendor_List"],
    "docx": ["Memo", "Offer_Letter", "NDA", "SOP", "Meeting_Notes", "Performance_Review"],
    "sql": ["schema_dump", "migration_{n}", "backup_query", "user_export", "prod_snapshot"],
    "conf": ["nginx.conf", "database.yml", "secrets.env", "app.config", "vpn.conf"],
    "pem": ["server.crt", "ca-bundle.pem", "private.key", "ssl_cert.pem"],
    "apk": ["mobile-app-v{n}", "beta-release.apk"],
    "pcap": ["network_capture", "traffic_dump"],
    "csv": ["customer_list", "employee_data", "transaction_log", "vendor_master"],
    "bak": ["database.bak", "config_backup", "registry_backup"],
    "db": ["Thumbs.db", "cache.db", "session_store.db"],
    "py": ["deploy_script", "etl_pipeline", "data_migration", "api_handler"],
    "jpg": ["ID_Photo", "Signature", "Address_Proof", "Receipt_Scan"],
    "zip": ["archive_{year}", "migration_bundle", "code_release"],
}

FLAG_NAMES = {
    "vapt_report": "VAPT_Report_2024",
    "pentest": "PenTest_Findings_Final",
    "password": "passwords.txt",
    "credentials": "admin_credentials.json",
    "firewall": "firewall_rules.conf",
    "vpn_config": "vpn_client_config.ovpn",
    "database_dump": "production_db_dump.sql",
    "mysqldump": "full_mysqldump.sql",
}


def _size_for(ext: str) -> int:
    ranges = {
        "pdf": (50_000, 5_000_000), "xlsx": (20_000, 2_000_000),
        "docx": (10_000, 500_000), "sql": (100_000, 50_000_000),
        "conf": (500, 50_000), "pem": (1_000, 10_000),
        "apk": (5_000_000, 50_000_000), "pcap": (1_000_000, 100_000_000),
        "csv": (10_000, 10_000_000), "bak": (1_000_000, 100_000_000),
        "db": (10_000, 500_000), "py": (1_000, 50_000),
        "jpg": (20_000, 500_000), "zip": (1_000_000, 200_000_000),
    }
    lo, hi = ranges.get(ext, (1_000, 100_000))
    return random.randint(lo, hi)


def _name_for(ext: str, path_ctx: str) -> str:
    templates = FILE_TEMPLATES.get(ext, ["document"])
    tmpl = random.choice(templates)
    return tmpl.format(
        q=random.randint(1, 4),
        n=random.randint(1, 9),
        month=random.choice(["Jan", "Feb", "Mar", "Apr", "May", "Jun"]),
        year=random.choice(YEARS),
    ) + f".{ext}"


def generate() -> dict:
    dirs: list[str] = [""]
    files: dict[str, dict] = {}
    base_url = "http://demo.example.org/acme-corp"

    for dept in DEPARTMENTS:
        dept_path = dept
        dirs.append(dept_path)
        for region in random.sample(REGIONS, k=random.randint(2, 4)):
            region_path = f"{dept_path}/{region}"
            dirs.append(region_path)
            for year in random.sample(YEARS, k=random.randint(1, 2)):
                year_path = f"{region_path}/{year}"
                dirs.append(year_path)

                # 15-30 files per leaf
                for _ in range(random.randint(15, 30)):
                    ext = random.choices(
                        list(FILE_TEMPLATES.keys()),
                        weights=[15, 12, 10, 5, 3, 2, 1, 1, 8, 4, 3, 6, 10, 5],
                    )[0]
                    name = _name_for(ext, year_path)
                    relpath = f"{year_path}/{name}"
                    if relpath in files:
                        name = f"{name.split('.')[0]}_{random.randint(1,999)}.{ext}"
                        relpath = f"{year_path}/{name}"
                    files[relpath] = {
                        "name": name,
                        "url": f"{base_url}/{relpath}",
                        "size": str(_size_for(ext)),
                    }

    # ── Inject intentional duplicates (same name, different folders) ──
    dup_names = ["Policy.pdf", "Budget_v1.xlsx", "SOP.docx", "Thumbs.db", "backup_query.sql"]
    for dname in dup_names:
        ext = dname.rsplit(".", 1)[-1]
        sz = str(_size_for(ext))
        for folder in random.sample(dirs[1:], k=random.randint(3, 8)):
            relpath = f"{folder}/{dname}" if folder else dname
            if relpath not in files:
                files[relpath] = {
                    "name": dname,
                    "url": f"{base_url}/{relpath}",
                    "size": sz,
                }

    # ── Inject security-flaggable files ──────────────────────────────
    flag_dir = "IT-Infra/Security"
    dirs.append(flag_dir)
    for key, fname in FLAG_NAMES.items():
        ext = fname.rsplit(".", 1)[-1] if "." in fname else "txt"
        relpath = f"{flag_dir}/{fname}"
        files[relpath] = {
            "name": fname,
            "url": f"{base_url}/{relpath}",
            "size": str(_size_for(ext if ext in FILE_TEMPLATES else "conf")),
        }

    # A few more scattered flaggable files
    for fname in ["VAPT_Report_2023.pdf", "production_db_dump.sql", "nginx.conf",
                   "admin_credentials.json", "PenTest_Findings.docx"]:
        folder = random.choice(dirs[1:])
        ext = fname.rsplit(".", 1)[-1]
        relpath = f"{folder}/{fname}"
        if relpath not in files:
            files[relpath] = {
                "name": fname,
                "url": f"{base_url}/{relpath}",
                "size": str(_size_for(ext)),
            }

    # Remove empty root dir entry, normalize
    dirs = sorted(set(dirs))

    return {
        "depth": 4,
        "dirs": dirs,
        "files": files,
        "stats": {
            "dirs": len(dirs),
            "files": len(files),
        },
    }


if __name__ == "__main__":
    import json
    data = generate()
    print(f"Generated {data['stats']['files']:,} files / {data['stats']['dirs']:,} dirs")
    print(json.dumps(data, indent=2)[:500])
