import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve, sep, extname } from "node:path";
import { chromium } from "@playwright/test";
import { gzipSync } from "node:zlib";

const root = resolve("dist");
const server = createServer((request, response) => {
  try {
    const path = resolve(
      root,
      "." + new URL(request.url, "http://localhost").pathname,
    );
    if (!path.startsWith(root + sep) && path !== root) {
      response.writeHead(403).end();
      return;
    }
    const target = path === root ? resolve(root, "index.html") : path;
    const type =
      {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".woff2": "font/woff2",
        ".svg": "image/svg+xml",
      }[extname(target)] ?? "application/octet-stream";
    const content = readFileSync(target);
    if (
      /text|javascript|json/.test(type) &&
      request.headers["accept-encoding"]?.includes("gzip")
    ) {
      response
        .writeHead(200, {
          "Content-Type": type,
          "Content-Encoding": "gzip",
          Vary: "Accept-Encoding",
        })
        .end(gzipSync(content));
      return;
    }
    response.writeHead(200, { "Content-Type": type }).end(content);
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise((resolve) => server.listen(4175, "127.0.0.1", resolve));
mkdirSync("lighthouse-results", { recursive: true });
const summary = {};
try {
  for (const route of [
    "market",
    "drops",
    "seasons",
    "drivers",
    "fair",
    "about",
  ]) {
    const output = resolve(`lighthouse-results/${route}.json`);
    const args = [
      process.env.npm_execpath,
      "exec",
      "--yes",
      "--package=node@22.23.4",
      "--package=lighthouse@13.5.0",
      "--",
      "lighthouse",
      `http://127.0.0.1:4175/#${route}`,
      "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage",
      "--only-categories=performance,accessibility,best-practices",
      "--output=json",
      `--output-path=${output}`,
      "--quiet",
    ];
    const exit = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, args, {
        stdio: "inherit",
        env: { ...process.env, CHROME_PATH: chromium.executablePath() },
      });
      child.on("error", reject);
      child.on("exit", resolve);
    });
    if (exit !== 0) throw new Error(`Lighthouse failed for ${route}`);
    const report = JSON.parse(readFileSync(output, "utf8"));
    const scores = Object.fromEntries(
      Object.entries(report.categories).map(([key, value]) => [
        key,
        Math.round(value.score * 100),
      ]),
    );
    summary[route] = scores;
    console.log(route, scores);
    if (Object.values(scores).some((score) => score < 95))
      throw new Error(`${route} failed the Lighthouse 95 target`);
  }
} finally {
  writeFileSync(
    "lighthouse-results/summary.json",
    JSON.stringify(summary, null, 2) + "\n",
  );
  server.close();
}
