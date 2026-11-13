// What a pleasure boater needs at a lock: how to call it and what the
// signals mean.
//
// Sources (checked 2026-11-12):
// - 33 CFR 207.300 (Mississippi River locks): pull chain, horn signals,
//   signal lights, recreational strobe, lockage order, mooring.
//   https://www.law.cornell.edu/cfr/text/33/207.300
// - VHF: USACE Rock Island District brochure (Ch 14 from Upper St. Anthony
//   Falls to Lock 24 and Mel Price; Ch 12 for Locks 25 and 27); St. Paul
//   District Lock & Dam 1 page (Ch 14, phone, recreation pull cord); St. Louis
//   District "Locking Through" flier (Lock 25 marine radio 12). For Lock 24
//   and Mel Price, USACE sources disagree (12 vs 14), so the app says so.
// Phone numbers come from the lock list (backend/config.py LOCKS).
export const CFR_URL = "https://www.law.cornell.edu/cfr/text/33/207.300";

const CH12 = new Set(["lock_25", "chain_of_rocks"]);
const UNSURE = new Set(["lock_24", "melvin_price"]);

export function vhfFor(lockId) {
  if (CH12.has(lockId)) return { channel: "12", note: null };
  if (UNSURE.has(lockId)) return { channel: "14", note: "Some USACE notices list channel 12 for this lock; call if no answer on 14." };
  return { channel: "14", note: null };
}

export function telHref(phone) {
  const digits = String(phone || "").replace(/[^0-9]/g, "");
  return digits.length >= 10 ? `tel:${digits}` : null;
}

// Plain-language steps, in the order a boater meets them.
export function lockingSteps(lockId) {
  const { channel } = vhfFor(lockId);
  return [
    {
      title: "Ask for a lockage",
      text: `Call the lock on VHF ${channel} or by phone. No radio: pull the cord or chain at the end of the lock wall (most locks have one at each end).`,
    },
    {
      title: "Wait clear of the lock",
      text: "Hold well off the lock and out of the way of tows; don't tie up within 1,200 ft of the lock unattended. Listen on VHF 13 for what the tows are doing.",
    },
    {
      title: "Watch the lights",
      text: "Red: stand clear. Amber: lock is being made ready, approach under control. Green: enter. A flashing strobe on the lock means recreational boats may enter.",
    },
    {
      title: "Horn signals from the lock",
      text: "One long blast: enter. One short blast: leave. Four or more short blasts: danger, stop.",
    },
    {
      title: "Who goes first",
      text: "Commercial tows normally lock before pleasure boats. You may be locked through with a tow if both agree; otherwise you get your own lockage after no more than three other lockages.",
    },
    {
      title: "In the chamber",
      text: "Moor with bow and stern lines leading in opposite directions as the lock staff directs. Never tie to the ladders. Keep the props still unless told otherwise; don't pass other boats.",
    },
  ];
}
