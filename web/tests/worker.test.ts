import { afterEach, expect, it, vi } from "vitest";
import { clearCache, loadBundle } from "../src/lib/data";
import { coherent, keys, validate } from "../src/lib/validation";
import type { Bundle } from "../src/lib/data";
const fixtures = import.meta.glob("./fixtures/*.json", {
  eager: true,
  import: "default",
});
const populated = coherent(
  Object.fromEntries(
    keys.map((key) => [key, validate(key, fixtures[`./fixtures/${key}.json`])]),
  ) as Bundle,
);

class FakeWorker {
  static current: FakeWorker;
  onmessage?: (event: { data: unknown }) => void;
  onerror?: () => void;
  terminate = vi.fn();
  postMessage = vi.fn();
  constructor() {
    FakeWorker.current = this;
  }
}
afterEach(() => {
  clearCache();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it("caches worker validation, resolves a coherent bundle and releases the worker", async () => {
  vi.stubGlobal("Worker", FakeWorker);
  const promise = loadBundle();
  expect(loadBundle()).toBe(promise);
  const worker = FakeWorker.current;
  expect(worker.postMessage).toHaveBeenCalledWith({
    base: new URL(import.meta.env.BASE_URL, document.baseURI).href,
  });
  worker.onmessage!({ data: { bundle: populated } });
  expect(await promise).toEqual(populated);
  expect(worker.terminate).toHaveBeenCalledOnce();
});
it("propagates validation failures and allows a fresh retry", async () => {
  vi.stubGlobal("Worker", FakeWorker);
  const promise = loadBundle();
  FakeWorker.current.onmessage!({
    data: { error: "The data is being refreshed. Please retry." },
  });
  await expect(promise).rejects.toThrow("refreshed");
  const retry = loadBundle();
  FakeWorker.current.onerror!();
  await expect(retry).rejects.toThrow("connection");
  expect(FakeWorker.current.terminate).toHaveBeenCalledOnce();
});
it("stops an unresponsive worker", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("Worker", FakeWorker);
  const promise = loadBundle();
  const rejected = expect(promise).rejects.toThrow("too long");
  await vi.advanceTimersByTimeAsync(30000);
  await rejected;
  expect(FakeWorker.current.terminate).toHaveBeenCalledOnce();
});
it("falls back to schema validation if worker creation is blocked", async () => {
  vi.stubGlobal(
    "Worker",
    class {
      constructor() {
        throw new Error("blocked");
      }
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false })),
  );
  await expect(loadBundle()).rejects.toThrow("connection");
});
