import {
  urlBase64ToUint8Array, sameKey, pushPrefs, pushStatusText, PUSH_STATUS_TEXT,
} from "./push";
import { ALERT_DEFAULTS } from "./alerts";

describe("urlBase64ToUint8Array", () => {
  it("decodes base64url without padding", () => {
    expect(Array.from(urlBase64ToUint8Array("AQID_-8"))).toEqual([1, 2, 3, 255, 239]);
    expect(Array.from(urlBase64ToUint8Array(""))).toEqual([]);
  });

  it("decodes a 65-byte VAPID public key", () => {
    const key = `B${"A".repeat(86)}`;
    const bytes = urlBase64ToUint8Array(key);
    expect(bytes.length).toBe(65);
    expect(bytes[0]).toBe(4);
  });
});

describe("sameKey", () => {
  it("compares a subscription's key buffer with the server key", () => {
    const buf = new Uint8Array([1, 2, 3, 255, 239]).buffer;
    expect(sameKey(buf, "AQID_-8")).toBe(true);
    expect(sameKey(buf, "AQID_-0")).toBe(false);
    expect(sameKey(buf, "AQID")).toBe(false);
    expect(sameKey(null, "AQID")).toBe(false);
  });
});

describe("pushPrefs", () => {
  it("mirrors the bell settings and the planner's direction", () => {
    const p = pushPrefs({ ...ALERT_DEFAULTS, enabled: true, towMiles: 5 }, { direction: "upbound", mph: 20 });
    expect(p).toEqual({
      tow: true, towMiles: 5, lock: true, lockWaitMinutes: 30, depart: true, sound: false,
      direction: "upbound", mph: 20,
    });
    expect(Object.keys(p)).not.toContain("enabled");
  });
});

describe("pushStatusText", () => {
  it("says clearly whether alerts arrive with the app closed", () => {
    expect(pushStatusText("active")).toBe("Alerts reach you even when River Watch is closed.");
    for (const s of ["off", "no-server", "unsupported", "permission", "error", "no-boat"]) {
      expect(pushStatusText(s)).toMatch(/^Alerts arrive only while River Watch is open/);
    }
    expect(pushStatusText("weird")).toBe(PUSH_STATUS_TEXT.off);
  });
});
