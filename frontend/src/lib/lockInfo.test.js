import { vhfFor, telHref, lockingSteps } from "./lockInfo";

test("VHF channel by lock, with a note where USACE sources disagree", () => {
  expect(vhfFor("lock_2")).toEqual({ channel: "14", note: null });
  expect(vhfFor("lock_25").channel).toBe("12");
  expect(vhfFor("chain_of_rocks").channel).toBe("12");
  expect(vhfFor("melvin_price").note).toMatch(/channel 12/);
});

test("tel links need a full number", () => {
  expect(telHref("651-290-5828")).toBe("tel:6512905828");
  expect(telHref("")).toBeNull();
  expect(telHref(null)).toBeNull();
});

test("steps name the lock's own channel", () => {
  const s = lockingSteps("lock_25");
  expect(s[0].text).toMatch(/VHF 12/);
  expect(s.map((x) => x.title)).toContain("Who goes first");
});
