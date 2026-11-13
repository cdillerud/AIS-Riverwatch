import { act } from "react";
import { createRoot } from "react-dom/client";
import FirstRunWizard from "./FirstRunWizard";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() } }));

const MARINAS = { marinas: [{ osm_id: "w/1", name: "Twin City Marina", river_mile: 830.3, lat: 44.855, lon: -93.012 },
  { osm_id: "w/2", name: "Hastings Marina", river_mile: 813.4, lat: 44.74, lon: -92.85 }] };

function setValue(el, value) {
  const proto = el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
}

test("a boat with no MMSI goes from name to plan in three steps", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  const calls = [];
  global.fetch = jest.fn((url, opts = {}) => {
    calls.push([String(url), opts.method || "GET", opts.body]);
    let body = {};
    if (String(url).includes("/marinas")) body = MARINAS;
    else if (String(url).includes("/locks")) body = [];
    else if (String(url).endsWith("/user/vessels")) body = { vessel: { mmsi: "000123456", boat_name: "Sea Biscuit" } };
    else if (String(url).includes("/home-berth")) body = { home_berth: { river_mile: 830.3 } };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  const done = jest.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<FirstRunWizard onDone={done} onBack={() => {}} />); });
  const q = (id) => el.querySelector(`[data-testid="${id}"]`);

  await act(async () => { setValue(q("fr-name"), "Sea Biscuit"); });
  await act(async () => { q("fr-next-boat").click(); });
  const add = calls.find((c) => c[0].endsWith("/user/vessels"));
  expect(JSON.parse(add[2])).toMatchObject({ mmsi: null, boat_name: "Sea Biscuit" });

  await act(async () => { setValue(q("fr-place"), "m:w/1"); });
  await act(async () => { q("fr-use-place").click(); });
  expect(calls.some((c) => c[0].includes("/user/vessels/000123456/home-berth") && c[1] === "PUT")).toBe(true);

  await act(async () => { setValue(q("fr-dest"), "m:w/2"); });
  await act(async () => { q("fr-finish").click(); });
  expect(done).toHaveBeenCalledWith({ user_mmsi: "000123456", boat_name: "Sea Biscuit" });
  expect(JSON.parse(localStorage.getItem("activeTrip"))).toMatchObject({ end_rm: 813.4, heading: "southbound" });
  expect(JSON.parse(localStorage.getItem("departurePrefs"))).toMatchObject({ direction: "downbound", mph: 15 });
  act(() => root.unmount());
});
