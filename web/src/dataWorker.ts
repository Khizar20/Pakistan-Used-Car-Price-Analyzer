import { fetchBundle } from "./lib/validation";
import type { WorkerReply } from "./lib/data";

self.onmessage = async (event: MessageEvent<{ base: string }>) => {
  let reply: WorkerReply;
  try {
    reply = { bundle: await fetchBundle(event.data.base) };
  } catch (error: unknown) {
    reply = {
      error:
        error instanceof Error
          ? error.message
          : "The data could not be verified. Please retry.",
    };
  }
  self.postMessage(reply);
};
