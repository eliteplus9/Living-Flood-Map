import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 120000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:5173", browserName: "chromium", channel: "msedge", screenshot: "only-on-failure" },
  reporter: "list",
});
