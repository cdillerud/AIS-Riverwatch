// Boats without AIS get an app ID (000 + 6 digits; no real MMSI starts with
// 000). Show "no AIS" instead of a number that looks like an MMSI.
export const isAppId = (mmsi) => /^000\d{6}$/.test(String(mmsi || ""));
export const mmsiLabel = (mmsi) => (isAppId(mmsi) ? "no AIS" : String(mmsi || ""));
