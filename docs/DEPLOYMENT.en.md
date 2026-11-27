# Deploy Forma AI

[简体中文](DEPLOYMENT.md) · [README](../README.en.md)

Run the commands from the project root after cloning the repository or extracting the source ZIP. Both deployment modes serve the UI and `/api` on the same port. The built-in Mock provider runs without external credentials or a GPU.

## Windows without Docker

Install Python 3.12, Node.js 22.12 or later in the 22.x series, and npm. Run in PowerShell.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

The script installs dependencies, builds the frontend, migrates SQLite, and starts the app in the foreground. Open `http://localhost:8080/` and use `.runtime\local\setup.token` to set up the first super admin. Check the running app from another PowerShell window.

```powershell
Invoke-RestMethod http://localhost:8080/api/health
```

The app listens on loopback by default. Use `-Port 8081` to choose another port, `-Lan` for trusted local-network access, or `-Python` and `-Npm` to specify absolute executable paths. Press Ctrl+C to stop. Restart from the same directory to reuse the SQLite database, images, and encryption key in `.runtime\local\`.

## Docker Compose on Windows

Install and start Docker Desktop in Linux container mode with its WSL 2 or Hyper-V backend. Verify that `docker version` shows a server and `docker compose version` succeeds. [Docker Desktop installation](https://docs.docker.com/desktop/setup/install/windows-install/)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
docker compose ps
Invoke-RestMethod http://localhost:8080/api/health
```

The script creates `.env` with a random database password and setup token on first run, then builds and starts the app and PostgreSQL 17. Alembic migrates the database after PostgreSQL is healthy. Open `http://localhost:8080/` and enter your local `APP_SETUP_TOKEN` to create the super admin.

Use `-Port 8081` on the first run or change `APP_PORT` in an existing `.env`. The Windows Docker script binds to all interfaces by default. For loopback-only access, set `APP_BIND=127.0.0.1` and run `docker compose up -d --wait` again. For LAN access, allow the application port on the trusted Windows firewall profile and use the host's actual IPv4 address from the client device.

## Docker Compose on Linux

Install Docker Engine, the Compose plugin, and `openssl`. Create `.env` with unique local secrets. This block preserves an existing `.env` and writes a new file with owner-only permissions.

```sh
(
  set -euC
  umask 077
  if [ ! -e .env ]; then
    forma_db_password=$(openssl rand -hex 32)
    forma_setup_token=$(openssl rand -hex 32)
    cat > .env <<EOF
APP_PORT=8080
APP_BIND=127.0.0.1
APP_COOKIE_SECURE=0
APP_WORKER_SLOTS=4
POSTGRES_PASSWORD=$forma_db_password
APP_SETUP_TOKEN=$forma_setup_token
EOF
  fi
)
```

After the file is ready, build and verify the services.

```sh
docker compose up --build -d --wait
docker compose ps
curl -fsS http://127.0.0.1:8080/api/health
```

For first-run setup on a remote loopback-only host, forward an unused local port over SSH. Replace the user and hostname with your own.

```sh
ssh -N -L 18080:127.0.0.1:8080 your-user@server.example.com
```

Open `http://localhost:18080/` locally and use the `APP_SETUP_TOKEN` from the server's `.env`. Adjust the tunnel's destination port if you changed `APP_PORT`.

## Configuration and operations

| Variable | Purpose |
| --- | --- |
| `APP_PORT` / `APP_BIND` | Host port and listen address |
| `POSTGRES_PASSWORD` | Password set when the database volume is created, also used by the app |
| `APP_SETUP_TOKEN` | Token used for the first super-admin setup |
| `APP_COOKIE_SECURE` | Set to `1` when serving over HTTPS, use `0` for local HTTP |
| `APP_WORKER_SLOTS` | Number of job slots in the web process, default `4` and range `1–8` |

For shared deployments, put the app behind a trusted HTTPS reverse proxy, forward both the web app and `/api` on the same host. Allow request bodies up to 32 MiB in the proxy and set `APP_COOKIE_SECURE=1`. Apply the settings with `docker compose up -d --wait`. PostgreSQL is available on the internal Compose network.

```sh
docker compose ps
docker compose logs --tail 100 app
docker compose restart app
docker compose stop
docker compose up -d --wait
```

Keep the Compose project name and the `postgres_data`, `files_data`, and `instance_secrets` volumes when restarting or updating an instance. The app and database use the `unless-stopped` restart policy. Keep `.env` and deployment data out of source archives and Git. [Docker volume documentation](https://docs.docker.com/engine/storage/volumes/)

## Configure real AI providers

As super admin, open **管理后台 → API 服务商与模型** (Admin → API Providers and Models). Configure the provider, enter the key in the app, and add the model ID, supported capabilities, input limits, and output options. Use the connection and model tests with the appropriate operator approval.

- OpenAI uses its official endpoint. OpenAI Compatible takes a full API prefix such as `https://api.example.com/v1`.
- Gemini API defaults to the official endpoint. When a custom URL has no path, Forma AI appends `/v1beta`. Supply the full prefix when the service uses another path.
- For an HTTP provider that needs no authentication, leave the key field empty. Use trusted HTTPS when sending credentials or project images across a network. Re-enter the target service's key when changing a provider URL that has a saved key.
- Supported image responses for OpenAI Compatible include `b64_json` and public HTTPS download URLs. A host service at `127.0.0.1` is reachable only when it shares the backend's network context.

For the design workspace, configure image generation and editing capabilities, since generation includes a source photo. Iterating from a parent version can require a model that supports multiple images. Use the task defaults to choose a model per workflow. The system settings can pause external calls while Mock stays available. The Chinese guide includes the [VX API integration notes](DEPLOYMENT.md#vx-api-图片模型).

## Backup and recovery

Create a full snapshot from **管理后台 → 系统日志及备份 → 整站备份** (Admin → System Logs and Backups → Full Backup). Use the ZIP containing `manifest.json` for recovery. If the instance has saved provider keys, separately secure a copy of `/var/lib/forma/secrets/provider.key` in Compose or `.runtime/local/secrets/provider.key` in native mode.

Restore against an empty target database with an app image that matches the snapshot's migration version. The following PowerShell example assumes the snapshot is at `.runtime\recovery\files\snapshot.zip` and the key at `.runtime\recovery\keys\provider.key`.

```powershell
$backupDir = (Resolve-Path .\.runtime\recovery\files).Path
$keysDir = (Resolve-Path .\.runtime\recovery\keys).Path
$env:APP_PORT = '8081'
$env:APP_BIND = '127.0.0.1'
$env:APP_COOKIE_SECURE = '0'
docker compose -p forma-recovery build app
docker compose -p forma-recovery up -d --wait db
docker compose -p forma-recovery run --rm --no-deps -v "${backupDir}:/recovery/files:ro" -v "${keysDir}:/recovery/keys:ro" app python -m app.manage restore /recovery/files/snapshot.zip --key-file /recovery/keys/provider.key
docker compose -p forma-recovery up -d --wait app
```

If recovering without the key file, omit its mount and `--key-file`, then re-enter the provider credentials after recovery. Open `http://localhost:8081/`. Sign in with an account from the backup and verify projects, images, versions, and plans before switching traffic. Queued or in-progress jobs from the backup are restored as failed for review.

For native SQLite recovery, stop the target server, set `APP_DATA_DIR` and `APP_SECRET_DIR` to new directories, and run `..\.venv\Scripts\python.exe -m app.manage restore <snapshot-path>` from `backend/`. Pass `--key-file <key-path>` if available.

## Deployment checks

1. Confirm that `/api/health` returns HTTP 200 with `"status": "ok"`. On Docker, check that both services are healthy.
2. Sign in with a test account, try the demo, generate a Mock result, and download the image. For a LAN deployment, run this from a second device.
3. Restart the services and verify that the same account, project, version, and image remain available. Compare the image's SHA-256 before and after the restart when checking byte-for-byte persistence.

See the [test report](TEST.md) for the environments and checks already verified.
