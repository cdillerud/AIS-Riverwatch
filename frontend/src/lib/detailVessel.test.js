import { toDetailVessel } from "./detailVessel";

const LIVE = [{ mmsi: "366961540", name: "VIRGINIA INGRAM", river_mile: 839.1, lat: 44.9 }];

test("a boat with a live AIS position opens its live record", () => {
  expect(toDetailVessel({ mmsi: "366961540", vessel_name: "VIRGINIA INGRAM" }, LIVE)).toBe(LIVE[0]);
  expect(toDetailVessel({ vessel_name: "virginia ingram " }, LIVE)).toBe(LIVE[0]);   // by name
});

test("a live vessel object passes straight through", () => {
  expect(toDetailVessel(LIVE[0], [])).toBe(LIVE[0]);
});

test("a USACE-only boat gets a record from the queue row", () => {
  const v = toDetailVessel({ mmsi: 367000001, vessel_name: "SHOW ME STATE", barges: 12, direction: "downbound",
                             arrived_at: "2026-11-10T22:00:00+00:00" }, LIVE, "Lock & Dam #17");
  expect(v).toMatchObject({ mmsi: "367000001", name: "SHOW ME STATE", barge_count: 12, is_tow: true,
                            direction: "downbound", usace_status: "waiting", usace_lock: "Lock & Dam #17",
                            no_ais_position: true, river_mile: null });
});

test("lock-detail rows (num_barges, U/D) are understood", () => {
  const v = toDetailVessel({ name: "MARGIT B", num_barges: 2, direction: "U", sol_date: "x" }, [], "Lock 6");
  expect(v).toMatchObject({ name: "MARGIT B", barge_count: 2, direction: "upbound", usace_status: "locking" });
});
