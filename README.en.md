# Forma AI

[简体中文](README.md) · [Deployment guide](docs/DEPLOYMENT.en.md)

Forma AI is a Chinese-language workspace for industrial design and hardware development. Teams can turn product photos and references into design concepts, iterate on each result, and plan materials, bills of materials (BOMs), and costs.

## Features

- **Design generation** Combine source photos, reference images, design directions, and the details to preserve. Follow the status of each generation job.
- **Version history** Keep the original output, generation parameters, and parent version for each design. Branch from earlier results, compare images side by side, favorite them, or download them.
- **Materials and costing** Edit component and material recommendations, exchange price lists through Excel, and save separate cost plans.
- **Team workspace** Manage accounts and project access, export individual projects as ZIPs, and create and restore full-instance backups.
- **AI providers** Start with the built-in Mock provider. Super admins can configure OpenAI, OpenAI Compatible, and Gemini API providers and models.

## Quick start

Clone the repository or extract the source ZIP. Run the relevant command from the directory that contains `compose.yaml`.

**Windows without Docker** requires Python 3.12, Node.js 22.12 or later in the 22.x series, and npm. This mode uses SQLite.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Open `http://localhost:8080/` and use the token in `.runtime\local\setup.token` to create the super admin. The script listens on loopback by default.

**Docker Compose on Windows** requires Docker Desktop in Linux container mode. This mode uses PostgreSQL 17.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Open `http://localhost:8080/`. The first-run token is `APP_SETUP_TOKEN` in your local `.env`. See the [deployment guide](docs/DEPLOYMENT.en.md) for Linux, networking, HTTPS, and recovery.

After signing in, select **试用示例** (Try the demo) to use Mock for prompt refinement, design generation, branching, material analysis, and costing. Mock runs locally without an API key or GPU.

## Workflow

1. An admin creates member accounts with temporary passwords. Members choose a new password at first sign-in.
2. Create a project in **我的项目** (My Projects). Upload product photos and optional references, then choose the design direction, redesign level, and output settings.
3. Compare generated images with the originals and branch from any result to keep iterating.
4. Edit components, materials, and prices in material analysis or costing. Save a plan or export the project.

## Credentials and data

Generate instance passwords and setup tokens during deployment. Enter provider API keys in your running instance. Keep real `.env` files, `.runtime/`, databases, key files, backups, and project images in the deployment environment. The application sends selected project inputs to an external provider only after an operator confirms the request.

## Developer documentation

The `frontend/` uses React, TypeScript, and Vite. The `backend/` uses FastAPI, SQLAlchemy, and Alembic. In production, FastAPI serves the web app and the same-origin `/api` routes.

- [Product requirements](docs/PRD.md) · [UI specification](docs/UI.md) · [Prompt design](docs/PROMPTS.md)
- [Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE.md) · [API](docs/API.md)
- [Testing](docs/TEST.md) · [Development progress](docs/PROGRESS.md)

The developer documentation linked above is in Chinese.
