import { randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const port = process.env.FORMA_E2E_PORT ?? "8185";
const baseURL = `http://127.0.0.1:${port}`;
const setupToken = process.env.FORMA_TEST_SETUP_TOKEN ?? randomBytes(32).toString("hex");
process.env.FORMA_TEST_SETUP_TOKEN = setupToken;

export default defineConfig({
  testDir: "./tests",
  timeout: 100_000,
  expect: { timeout: 12_000 },
  workers: 1,
  use: { baseURL, viewport: { width: 1440, height: 900 }, trace: "retain-on-failure" },
  reporter: "list",
  webServer: {
    command: "node tests/server.mjs",
    url: baseURL + "/api/health",
    env: {
      APP_DATA_DIR: mkdtempSync(join(tmpdir(), "forma-ui-test-")),
      APP_SETUP_TOKEN: setupToken,
      FORMA_E2E_PORT: port,
    },
    timeout: 45_000,
    reuseExistingServer: false,
  },
});
