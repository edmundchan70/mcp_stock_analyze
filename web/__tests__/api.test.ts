import { afterEach, describe, expect, it, vi } from "vitest";
import { createRun, getRun, listRuns, subscribeToRunEvents } from "@/lib/api";

const BASE = "http://localhost:8000";

function mockFetch(body: unknown, status = 200) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("lib/api", () => {
  it("listRuns returns the runs array", async () => {
    mockFetch({ runs: [{ id: "1" }] });
    const runs = await listRuns();
    expect(runs).toEqual([{ id: "1" }]);
    expect(fetch).toHaveBeenCalledWith(`${BASE}/api/runs`);
  });

  it("getRun hits the detail endpoint", async () => {
    mockFetch({ id: "1", artifacts: {} });
    const run = await getRun("1");
    expect(run.id).toBe("1");
    expect(fetch).toHaveBeenCalledWith(`${BASE}/api/runs/1`);
  });

  it("createRun posts JSON with the right body", async () => {
    mockFetch({ id: "9" }, 201);
    const run = await createRun({ pipeline_type: "daily_bo_scan", force_symbols: "AAPL" });
    expect(run.id).toBe("9");
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${BASE}/api/runs`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ pipeline_type: "daily_bo_scan", force_symbols: "AAPL" });
  });

  it("createRun throws on non-2xx", async () => {
    mockFetch({ detail: "bad" }, 422);
    await expect(createRun({ force_symbols: "" })).rejects.toThrow("422");
  });

  it("subscribeToRunEvents wires EventSource and forwards events", () => {
    const handlers: Record<string, (ev: Event) => void> = {};
    const close = vi.fn();
    const FakeEventSource = vi.fn().mockImplementation(() => ({
      addEventListener: (type: string, cb: (ev: Event) => void) => {
        handlers[type] = cb;
      },
      close,
    }));
    vi.stubGlobal("EventSource", FakeEventSource);

    const onEvent = vi.fn();
    const unsub = subscribeToRunEvents("1", onEvent);

    handlers["progress"]({ data: JSON.stringify({ type: "stage", text: "hi" }) } as MessageEvent);
    handlers["done"]({ data: JSON.stringify({ type: "done", counts: { 5: 1 } }) } as MessageEvent);

    expect(onEvent).toHaveBeenCalledWith({ type: "stage", text: "hi" });
    expect(onEvent).toHaveBeenCalledWith({ type: "done", counts: { 5: 1 } });
    unsub();
    expect(close).toHaveBeenCalled();
  });
});
