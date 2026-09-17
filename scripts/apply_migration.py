"""Apply one scripts/sql/*.sql file to the live Supabase DB via psycopg.

    poetry run python scripts/apply_migration.py sql/002_role_enrichment.sql

Reuses the .env parsing / conninfo logic from migrate_dashboard_data.py rather
than importing it (that module has a __main__ migration run as a side effect
of nothing, but keeping this a truly standalone script avoids any accidental
coupling to the one-off migration's globals).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def build_conninfo(env: dict[str, str]) -> str:
    ref = re.match(r"https://([^.]+)\.supabase\.co", env["SUPABASE_URL"]).group(1)
    password = env.get("SUPABASE_PASSWORD") or env["SUPABASE_PROJECT_PASSWORD"]
    return (
        f"postgresql://postgres.{ref}:{password}"
        f"@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
    )


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python scripts/apply_migration.py <sql/xxx.sql>")
        raise SystemExit(1)

    sql_path = BACKEND_ROOT / "scripts" / sys.argv[1]
    if not sql_path.exists():
        sql_path = BACKEND_ROOT / "scripts" / "sql" / sys.argv[1]  # bare filename shorthand
    sql = sql_path.read_text(encoding="utf-8")

    env = load_env(BACKEND_ROOT / ".env")
    conninfo = build_conninfo(env)

    print(f"Applying {sql_path} ...")
    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()
