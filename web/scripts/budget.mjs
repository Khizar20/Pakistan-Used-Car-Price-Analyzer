import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
const bytes = readdirSync("dist/assets")
  .filter((file) => file.endsWith(".js"))
  .reduce(
    (sum, file) => sum + gzipSync(readFileSync(`dist/assets/${file}`)).length,
    0,
  );
console.log(`Total JavaScript gzip: ${(bytes / 1000).toFixed(1)} KB / 250 KB`);
if (bytes >= 250_000) throw new Error("JavaScript bundle exceeds 250 KB gzip");
