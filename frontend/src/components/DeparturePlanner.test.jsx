import { act } from "react";
import { createRoot } from "react-dom/client";
import DeparturePlanner from "./DeparturePlanner";

const DATA = {
  start_rm: 830.3, destination_rm: null, best: 1, generated_at: "2026-11-12T15:00:00Z",
  locks: [{ lock_id: "lock_2", name: "Lock & Dam #2" }, { lock_id: "lock_3", name: "Lock & Dam #3" }],
  options: [
    { depart_in_minutes: 0, locks: [{ lock_id: "lock_2", arrive_minutes: 50, wait_minutes: 40 }, { lock_id: "lock_3", arrive_minutes: 150, wait_minutes: 1 }], time_at_locks_minutes: 81, finish_in_minutes: 200 },
    { depart_in_minutes: 30, locks: [{ lock_id: "lock_2", arrive_minutes: 50, wait_minutes: 2 }, { lock_id: "lock_3", arrive_minutes: 110, wait_minutes: 1 }], time_at_locks_minutes: 43, finish_in_minutes: 190 },
  ],
};

test("shows each departure with per-lock waits and marks the best", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(DATA) }));
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<DeparturePlanner userMmsi="338414076" destinationRm={null} />); });
  await act(async () => { await Promise.resolve(); });
  const row = (m) => el.querySelector(`[data-testid="departure-row-${m}"]`).textContent;
  expect(el.querySelector('[data-testid="departure-table"]')).not.toBeNull();
  expect(row(0)).toContain("Now");
  expect(row(0)).toContain("40m");
  expect(row(30)).toContain("★");
  const call = global.fetch.mock.calls.map((c) => c[0]).find((u) => u.includes("departure-options"));
  expect(call).toContain("direction=downbound");
  expect(el.querySelector('[data-testid="arrive-dark"]')).toBeNull(); // 9 am start, arrives ~12:30 pm
  act(() => root.unmount());
});
