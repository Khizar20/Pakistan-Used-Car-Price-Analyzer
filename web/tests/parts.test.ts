import { createHash, webcrypto } from "node:crypto";
import { TextEncoder, TextDecoder } from "node:util";
import { expect, it, vi } from "vitest";
import { fetchBundle, validate } from "../src/lib/validation";

const fixtures = import.meta.glob("./fixtures/*.json", {
  eager: true,
  import: "default",
});
const model = validate("models", fixtures["./fixtures/models.json"]);

function setup(failure = "none") {
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("TextDecoder", TextDecoder);
  const part = {
    schema_version: model.schema_version,
    generated_at: model.generated_at,
    bundle_id: failure === "mixed" ? "a".repeat(64) : model.bundle_id,
    data: failure === "schema" ? "invalid" : model.data.city_prices,
  };
  const content = new TextEncoder().encode(JSON.stringify(part));
  const digest = createHash("sha256").update(content).digest("hex");
  const root = {
    ...model,
    data: { ...model.data, city_prices: [], city_price_parts: [digest] },
  };
  const bytes =
    failure === "oversized"
      ? new Uint8Array(500000)
      : failure === "tampered"
        ? new TextEncoder().encode("changed")
        : content;
  const fetcher = vi.fn(async (url: string) =>
    url.includes("models-cities-")
      ? { ok: failure !== "http", arrayBuffer: async () => bytes.buffer }
      : {
          ok: true,
          json: async () =>
            url.endsWith("/models.json")
              ? root
              : fixtures[`./fixtures/${url.split("/").at(-1)}`],
        },
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

it("reassembles every verified cohort and keeps the logical bundle unchanged", async () => {
  const fetcher = setup();
  const bundle = await fetchBundle("/");
  expect(bundle.models).toEqual(model);
  expect(fetcher).toHaveBeenCalledTimes(9);
});

it.each([
  ["http", "could not be loaded"],
  ["oversized", "file budget"],
  ["tampered", "could not be verified"],
  ["schema", "format could not be verified"],
  ["mixed", "being refreshed"],
])(
  "rejects %s city data instead of rendering a partial comparison",
  async (failure, message) => {
    setup(failure);
    await expect(fetchBundle("/")).rejects.toThrow(message);
  },
);
