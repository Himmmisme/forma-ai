import { spawn, spawnSync } from "node:child_process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const python = process.env.FORMA_PYTHON ?? (process.platform === "win32"
  ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python"));
const cwd = join(root, "backend");
const env = { ...process.env, APP_SECRET_DIR: join(process.env.APP_DATA_DIR, "secrets"), APP_COOKIE_SECURE: "0",
  APP_WORKER_ENABLED: "1", DATABASE_URL: process.env.FORMA_E2E_DATABASE_URL ?? "" };
if (!env.DATABASE_URL) delete env.DATABASE_URL;
const migrated = spawnSync(python, ["-m", "app.manage", "migrate"], { cwd, env, stdio: "inherit" });
if (migrated.status !== 0) process.exit(migrated.status ?? 1);
const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port",
  process.env.FORMA_E2E_PORT, "--no-access-log"], { cwd, env, stdio: "inherit" });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code ?? 0));
