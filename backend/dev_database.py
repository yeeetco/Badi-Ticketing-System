"""Project-local PostgreSQL for Windows. No service or machine-wide install.

Run from the project root:
    backend/.venv/Scripts/python.exe backend/dev_database.py setup
    backend/.venv/Scripts/python.exe backend/dev_database.py start
    backend/.venv/Scripts/python.exe backend/dev_database.py stop

All downloaded binaries, database files, logs, and generated credentials live
in the ignored .local directory. Never use this helper for a production server.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import urllib.request
import zipfile

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
BIN = LOCAL / "pgsql" / "bin"
DATA = LOCAL / "postgres-data"
CONFIG = LOCAL / "postgres-config.json"
PORT = 55432
# EDB is the Windows binary distributor linked by postgresql.org.
ARCHIVE_URL = "https://get.enterprisedb.com/postgresql/postgresql-17.11-5-windows-x64-binaries.zip"


def run_pg(program, *arguments, check=True):
    return subprocess.run(
        [str(BIN / f"{program}.exe"), *map(str, arguments)],
        check=check, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def start():
    status = run_pg("pg_ctl", "-D", DATA, "status", check=False)
    if status.returncode != 0:
        run_pg("pg_ctl", "-D", DATA, "-l", LOCAL / "postgres.log",
               "-o", f"-p {PORT} -h 127.0.0.1", "-w", "start")


def setup():
    if os.name != "nt":
        raise SystemExit("This helper is Windows-only. See README for an existing PostgreSQL server.")
    LOCAL.mkdir(exist_ok=True)

    if not (BIN / "pg_ctl.exe").exists():
        archive = LOCAL / "postgresql.zip"
        if not archive.exists() or not zipfile.is_zipfile(archive):
            print("Downloading PostgreSQL binaries from EDB (approximately 382 MB)…", flush=True)
            urllib.request.urlretrieve(ARCHIVE_URL, archive)
        with zipfile.ZipFile(archive) as package:
            # Omit bundled pgAdmin and other tools; the database needs these only.
            for entry in package.infolist():
                if entry.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                    destination = (LOCAL / entry.filename).resolve()
                    if not destination.is_relative_to(LOCAL.resolve()):
                        raise RuntimeError("Archive path escapes the project directory.")
                    package.extract(entry, LOCAL)

    if not CONFIG.exists():
        if DATA.exists():
            raise SystemExit("Existing database data found without local config; refusing to reinitialize it.")
        CONFIG.write_text(json.dumps({
            "admin_password": secrets.token_urlsafe(24),
            "database_password": secrets.token_urlsafe(24),
        }), encoding="utf-8")
    credentials = json.loads(CONFIG.read_text(encoding="utf-8"))

    if not (DATA / "PG_VERSION").exists():
        password_file = LOCAL / "init-password.tmp"
        try:
            password_file.write_text(credentials["admin_password"], encoding="utf-8")
            run_pg("initdb", "-D", DATA, "-U", "badi_dev_admin", "-A", "scram-sha-256",
                   "--pwfile", password_file, "--encoding=UTF8", "--locale=C")
        finally:
            password_file.unlink(missing_ok=True)

    start()

    with psycopg.connect(host="127.0.0.1", port=PORT, dbname="postgres", user="badi_dev_admin",
                         password=credentials["admin_password"], autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = 'badi'").fetchone():
            connection.execute(sql.SQL("CREATE ROLE badi LOGIN PASSWORD {}").format(sql.Literal(credentials["database_password"])))
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname = 'badi'").fetchone():
            connection.execute("CREATE DATABASE badi OWNER badi")

    env_file = ROOT / "backend" / ".env"
    if not env_file.exists():
        env_file.write_text(
            f"DATABASE_URL=postgresql+psycopg://badi:{credentials['database_password']}@127.0.0.1:{PORT}/badi\n"
            "ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000\n"
            "COOKIE_SECURE=false\n", encoding="utf-8",
        )

    python = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    subprocess.run([str(python), "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT, check=True)

    agent_file = LOCAL / "agent-credentials.txt"
    if not agent_file.exists():
        agent_file.write_text(f"Email: agent@example.com\nPassword: {secrets.token_urlsafe(18)}\n", encoding="utf-8")
    agent_password = agent_file.read_text(encoding="utf-8").split("Password: ", 1)[1].strip()
    subprocess.run([str(python), "-m", "app.seed"], cwd=ROOT / "backend", check=True,
                   env={**os.environ, "DEMO_AGENT_PASSWORD": agent_password})
    print("Local PostgreSQL is ready on 127.0.0.1:55432.")
    print("Agent credentials are in .local/agent-credentials.txt (ignored by Git).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "start", "stop"])
    action = parser.parse_args().action
    if action == "setup":
        setup()
    elif action == "start":
        start()
    else:
        run_pg("pg_ctl", "-D", DATA, "-m", "fast", "-w", "stop")
