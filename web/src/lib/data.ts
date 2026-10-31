import type { Bundle } from "./validation";
export type { Bundle } from "./validation";
export type WorkerReply =
  { bundle: Bundle; error?: never } | { error: string; bundle?: never };

let cached: Promise<Bundle> | undefined;
export function clearCache() {
  cached = undefined;
}
function fallback(): Promise<Bundle> {
  return import("./validation").then(({ fetchBundle }) =>
    fetchBundle(import.meta.env.BASE_URL),
  );
}
function background(): Promise<Bundle> {
  if (typeof Worker === "undefined") return fallback();
  let worker: Worker;
  try {
    worker = new Worker(new URL("../dataWorker.ts", import.meta.url), {
      type: "module",
    });
  } catch {
    return fallback();
  }
  return new Promise((resolve, reject) => {
    const finish = () => {
      window.clearTimeout(timer);
      worker.terminate();
    };
    const timer = window.setTimeout(() => {
      finish();
      reject(
        new Error(
          "Loading the data took too long. Check your connection and retry.",
        ),
      );
    }, 30000);
    worker.onmessage = (event: MessageEvent<WorkerReply>) => {
      finish();
      if (event.data.error !== undefined) reject(new Error(event.data.error));
      else resolve(event.data.bundle);
    };
    worker.onerror = () => {
      finish();
      reject(
        new Error(
          "The market data could not be loaded. Check your connection and retry.",
        ),
      );
    };
    worker.postMessage({
      base: new URL(import.meta.env.BASE_URL, document.baseURI).href,
    });
  });
}
export function loadBundle(): Promise<Bundle> {
  cached ??= background().catch((error: unknown) => {
    clearCache();
    throw error;
  });
  return cached;
}
