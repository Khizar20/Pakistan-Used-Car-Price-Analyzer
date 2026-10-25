import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import Ajv from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import standalone from "ajv/dist/standalone/index.js";
import { _ } from "ajv/dist/compile/codegen/index.js";

const keys = [
  "meta",
  "index",
  "drops",
  "seasonality",
  "drivers",
  "fairprice",
  "models",
  "listings_sample",
];
const ajv = new Ajv({
  strict: false,
  allErrors: false,
  code: { source: true, esm: true, formats: _`fullFormats` },
});
addFormats(ajv);
for (const key of keys)
  ajv.addSchema(
    JSON.parse(readFileSync(`src/types/${key}.schema.json`, "utf8")),
    key,
  );
mkdirSync("src/generated", { recursive: true });
writeFileSync(
  "src/generated/validators.js",
  '// Generated from public JSON Schemas.\nimport { fullFormats } from "ajv-formats/dist/formats.js";\n' +
    standalone(ajv, Object.fromEntries(keys.map((key) => [key, key]))),
);
writeFileSync(
  "src/generated/validators.d.ts",
  keys
    .map((key) => `export const ${key}: (value: unknown) => boolean;`)
    .join("\n") + "\n",
);
