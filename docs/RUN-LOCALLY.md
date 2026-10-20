# Run the demo on your computer

[Back to the README](../README.md) · [Beginner's guide](BEGINNERS_GUIDE.md)

Choose one option below. Neither local option needs a cloud subscription or Entra registration. Use invented data only.

## Option 1: Windows PowerShell

Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/), the tool that installs this project's Python dependencies.

Clone the repository using Git (you need access to the repository), or download and extract its ZIP from GitHub's Code menu. Open PowerShell in the folder containing README.md and Start-Local.ps1.

```powershell
.\Start-Local.ps1
```

The script installs the locked dependencies, prepares the database tables, adds eight sample claims, and starts the server.

Open **http://127.0.0.1:8000**. Keep PowerShell open while using the app; press **Ctrl+C** there to stop it.

By default, data is stored in claims.db in the project folder and survives a restart. If DATABASE_URL is already set in your shell, the script uses that database instead. Use a disposable local database: this script enables development authentication.

If PowerShell cannot find uv, finish installing it and open a new terminal. If port 8000 is occupied, stop the other local server before trying again.

## Option 2: Docker Compose

With Docker and Docker Compose installed and running, open a terminal in the repository folder:

```powershell
docker compose up --build
```

Open **http://127.0.0.1:8000**. This option runs the app with PostgreSQL and stores database data in a Docker named volume.

To stop the services:

```powershell
docker compose down
```

The volume remains, preserving your test data. Adding --volumes would delete that data. The password in compose.yaml is for isolated local development only.

## What to try

File a fictitious claim, open its details in Claims Tracker, record a reviewer update, and reload the page. The claim and history should persist. Seeded records are not duplicated when you restart.

Local mode supplies all three roles automatically. It is useful for learning the workflow but does not verify Entra authentication. Azure setup is a separate path in [Deployment](DEPLOYMENT.md).

## Optional developer checks

```powershell
uv sync --frozen
uv run pytest -q -p no:cacheprovider
uv run ruff check app tests
```

The PostgreSQL-specific test requires a disposable PostgreSQL database; GitHub CI supplies one. Passing local tests alone does not verify Azure deployment or tenant sign-in.
