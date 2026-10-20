# Run the demo on your computer

[Back to the README](../README.md) · [Beginner's guide](BEGINNERS_GUIDE.md)

Choose either option. Both use a local development identity with all three roles and require no Azure account. Use fictitious data only.

## Option 1: Windows PowerShell

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Clone the repo or extract its ZIP, then open PowerShell in the folder containing `Start-Local.ps1`:

```powershell
.\Start-Local.ps1
```

The script installs locked dependencies, prepares the database, seeds eight claims, and starts the app. Open **http://127.0.0.1:8000**. Keep the terminal open; press **Ctrl+C** to stop.

Data stays in `claims.db` by default. If your shell already defines `DATABASE_URL`, the script uses that database instead. Use a disposable local database because this path enables development authentication. Repeated starts do not duplicate seeded claims.

If `uv` is not found, finish installing it and open a new terminal. If port 8000 is occupied, stop the other local server.

## Option 2: Docker Compose

With Docker and Compose installed and running:

```powershell
docker compose up --build
```

Open **http://127.0.0.1:8000**. Compose runs PostgreSQL and retains data in a named volume. Stop with:

```powershell
docker compose down
```

The volume remains. Adding `--volumes` deletes the saved data. Compose credentials are for isolated local development only.

## Try one workflow

File a synthetic claim, open its details, record a reviewer update, and reload. Confirm the claim and history persist. Local mode does not verify Entra sign-in; use [Azure onboarding](DEPLOYMENT.md#automated-onboarding) for that deployment.

## Developer checks

```powershell
uv sync --frozen
uv run pytest -q -p no:cacheprovider
uv run ruff check app tests scripts migrations
```

PostgreSQL-specific tests need a disposable PostgreSQL database; GitHub CI supplies one. See [Validation](VALIDATION.md) for what each check establishes.
