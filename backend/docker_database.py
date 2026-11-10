"""Manage Docker PostgreSQL while keeping FastAPI and Vite local.

    python backend/docker_database.py prepare  # create credentials only
    python backend/docker_database.py setup    # start, migrate, seed, connect API
    python backend/docker_database.py start    # start the existing database
    python backend/docker_database.py stop     # stop; keep data
    python backend/docker_database.py status

The old .local/postgres-data directory is never modified by this helper.
"""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

from dotenv import dotenv_values, set_key
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
COMPOSE_ENV = ROOT / ".env"
BACKEND_ENV = ROOT / "backend" / ".env"


def docker_path():
    executable = shutil.which("docker")
    if executable:
        return executable

    # A newly installed Docker may not be on this terminal's PATH yet.
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe",
        Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SystemExit("Docker CLI not found. Install Docker Desktop, then open a new terminal.")


def compose(*arguments):
    subprocess.run([docker_path(), "compose", "--project-directory", str(ROOT), *arguments], cwd=ROOT, check=True)


def prepare():
    # Preparing configuration must not change the working API connection.
    LOCAL.mkdir(exist_ok=True)
    COMPOSE_ENV.touch(exist_ok=True)
    current = dotenv_values(COMPOSE_ENV)
    for name in ("POSTGRES_ADMIN_PASSWORD", "POSTGRES_APP_PASSWORD"):
        if not current.get(name):
            set_key(str(COMPOSE_ENV), name, secrets.token_urlsafe(24))
    if not current.get("POSTGRES_PORT"):
        set_key(str(COMPOSE_ENV), "POSTGRES_PORT", "55433")
    print("Docker database credentials are ready in .env (ignored by Git).")
    print("FastAPI's current database connection has not changed.")


def setup():
    prepare()
    # Do not switch a working backend until the container is healthy and usable.
    compose("up", "-d", "--wait", "--wait-timeout", "120", "db")

    values = dotenv_values(COMPOSE_ENV)
    url = URL.create("postgresql+psycopg", username="badi", password=values["POSTGRES_APP_PASSWORD"],
                     host="127.0.0.1", port=int(values["POSTGRES_PORT"]), database="badi")
    database_url = url.render_as_string(hide_password=False)

    # Check the actual application credentials, not just PostgreSQL readiness.
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()

    python = sys.executable
    command_env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run([python, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
                   cwd=ROOT, env=command_env, check=True)

    # Reuse the local demo login, so testing Docker doesn't require a new password.
    agent_file = LOCAL / "agent-credentials.txt"
    if not agent_file.exists():
        agent_file.write_text(f"Email: agent@example.com\nPassword: {secrets.token_urlsafe(18)}\n", encoding="utf-8")
    password = agent_file.read_text(encoding="utf-8").split("Password: ", 1)[1].strip()
    subprocess.run([python, "-m", "app.seed"], cwd=ROOT / "backend",
                   env={**command_env, "DEMO_AGENT_PASSWORD": password}, check=True)

    # Preserve the previous connection so the user can return to the old database.
    backup = LOCAL / "backend-before-docker.env"
    if BACKEND_ENV.exists() and not backup.exists():
        shutil.copyfile(BACKEND_ENV, backup)
    if not BACKEND_ENV.exists():
        shutil.copyfile(ROOT / "backend" / ".env.example", BACKEND_ENV)
    set_key(str(BACKEND_ENV), "DATABASE_URL", database_url)

    print("Docker PostgreSQL is ready; backend/.env now points to it.")
    print("Restart FastAPI to load this connection. Vite does not need changes.")
    print("Existing Windows database data remains in .local/postgres-data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "setup", "start", "stop", "status"])
    action = parser.parse_args().action
    try:
        if action == "prepare":
            prepare()
        elif action == "setup":
            setup()
        elif action == "start":
            compose("up", "-d", "--wait", "--wait-timeout", "120", "db")
        elif action == "stop":
            compose("stop", "db")
        else:
            compose("ps")
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Command failed (exit {error.returncode}). Check that Docker Desktop is running and WSL is ready.") from None
