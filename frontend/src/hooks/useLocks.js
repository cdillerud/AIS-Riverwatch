import { useEffect, useState } from "react";
import { API } from "@/lib/api";

// Offline fallback only. GET /api/locks is authoritative (USACE river miles);
// this copy mirrors backend/config.py LOCKS and is used until the fetch
// resolves or when the backend is unreachable.
export const FALLBACK_LOCKS = [
  { id: "lock_1", name: "Lock & Dam #1 (Minneapolis)", river_mile: 847.6, lat: 44.9155, lon: -93.20085, phone: "612-724-2971" },
  { id: "lock_2", name: "Lock & Dam #2 (Hastings)", river_mile: 815.2, lat: 44.76097, lon: -92.86612, phone: "651-436-2900" },
  { id: "lock_3", name: "Lock & Dam #3 (Red Wing)", river_mile: 796.9, lat: 44.61193, lon: -92.61023, phone: "651-388-5794" },
  { id: "lock_4", name: "Lock & Dam #4 (Alma)", river_mile: 752.8, lat: 44.32422, lon: -91.92108, phone: "608-685-4421" },
  { id: "lock_5", name: "Lock & Dam #5 (Minnesota City)", river_mile: 738.1, lat: 44.16004, lon: -91.81104, phone: "507-689-2101" },
  { id: "lock_5a", name: "Lock & Dam #5A (Fountain City)", river_mile: 728.5, lat: 44.08867, lon: -91.66799, phone: "507-452-2789" },
  { id: "lock_6", name: "Lock & Dam #6 (Trempealeau)", river_mile: 714.0, lat: 43.99808, lon: -91.43883, phone: "608-534-6424" },
  { id: "lock_7", name: "Lock & Dam #7 (Dresbach)", river_mile: 702.0, lat: 43.86438, lon: -91.30794, phone: "507-895-2170" },
  { id: "lock_8", name: "Lock & Dam #8 (Genoa)", river_mile: 679.0, lat: 43.57177, lon: -91.22982, phone: "608-689-2625" },
  { id: "lock_9", name: "Lock & Dam #9 (Lynxville)", river_mile: 647.0, lat: 43.21331, lon: -91.10148, phone: "608-874-4311" },
  { id: "lock_10", name: "Lock & Dam #10 (Guttenberg)", river_mile: 615.0, lat: 42.786, lon: -91.0923, phone: "563-252-1261" },
  { id: "lock_11", name: "Lock & Dam #11 (Dubuque)", river_mile: 583.0, lat: 42.54078, lon: -90.64321, phone: "563-582-0881" },
  { id: "lock_12", name: "Lock & Dam #12 (Bellevue)", river_mile: 556.0, lat: 42.2605, lon: -90.42044, phone: "563-872-4384" },
  { id: "lock_13", name: "Lock & Dam #13 (Fulton)", river_mile: 522.0, lat: 41.89677, lon: -90.1578, phone: "815-589-2274" },
  { id: "lock_14", name: "Lock & Dam #14 (Le Claire)", river_mile: 493.0, lat: 41.57317, lon: -90.39875, phone: "563-289-4233" },
  { id: "lock_15", name: "Lock & Dam #15 (Rock Island)", river_mile: 482.9, lat: 41.51968, lon: -90.56518, phone: "309-794-5338" },
  { id: "lock_16", name: "Lock & Dam #16 (Muscatine)", river_mile: 457.2, lat: 41.42684, lon: -91.0123, phone: "563-263-7913" },
  { id: "lock_17", name: "Lock & Dam #17 (New Boston)", river_mile: 437.1, lat: 41.19138, lon: -91.05908, phone: "309-587-8461" },
  { id: "lock_18", name: "Lock & Dam #18 (Gladstone)", river_mile: 410.5, lat: 40.88113, lon: -91.0249, phone: "319-524-2933" },
  { id: "lock_19", name: "Lock & Dam #19 (Keokuk)", river_mile: 364.2, lat: 40.39043, lon: -91.37326, phone: "319-524-2933" },
  { id: "lock_20", name: "Lock & Dam #20 (Canton)", river_mile: 343.2, lat: 40.14168, lon: -91.51099, phone: "573-853-4213" },
  { id: "lock_21", name: "Lock & Dam #21 (Quincy)", river_mile: 324.9, lat: 39.90499, lon: -91.43033, phone: "217-228-0890" },
  { id: "lock_22", name: "Lock & Dam #22 (Saverton)", river_mile: 301.2, lat: 39.63695, lon: -91.2474, phone: "573-754-4451" },
  { id: "lock_24", name: "Lock & Dam #24 (Clarksville)", river_mile: 273.4, lat: 39.37528, lon: -90.90384, phone: "573-242-3564" },
  { id: "lock_25", name: "Lock & Dam #25 (Cap au Gris)", river_mile: 241.4, lat: 39.00369, lon: -90.68635, phone: "636-899-2301" },
  { id: "melvin_price", name: "Melvin Price Lock & Dam (Alton)", river_mile: 200.8, lat: 38.86761, lon: -90.15109, phone: "618-462-6979" },
  { id: "chain_of_rocks", name: "Chain of Rocks Lock (Granite City)", river_mile: 185.5, lat: 38.7003, lon: -90.19688, phone: "314-355-6100" },
];

let cachedLocks = null;
let inflight = null;

function normalize(list) {
  if (!Array.isArray(list) || list.length === 0) return null;
  return list.filter((l) => l && l.id && Number.isFinite(Number(l.river_mile)));
}

export function fetchLocks() {
  if (cachedLocks) return Promise.resolve(cachedLocks);
  if (!inflight) {
    inflight = fetch(`${API}/locks`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const locks = normalize(data);
        if (locks) cachedLocks = locks;
        return locks || FALLBACK_LOCKS;
      })
      .catch(() => FALLBACK_LOCKS)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

// Shared lock list: fetched once per page load, fallback until then.
export default function useLocks() {
  const [locks, setLocks] = useState(cachedLocks || FALLBACK_LOCKS);
  useEffect(() => {
    let cancelled = false;
    fetchLocks().then((l) => {
      if (!cancelled) setLocks(l);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return locks;
}

// Nearest lock ahead of a vessel at `riverMile` travelling `heading`.
// Northbound = upbound (higher river mile). Returns null when river mile is
// unknown or the heading is not directional.
export function findNextLock(locks, riverMile, heading) {
  const rm = riverMile == null ? NaN : Number(riverMile);
  if (!Number.isFinite(rm) || !Array.isArray(locks)) return null;
  let best = null;
  let bestDist = Infinity;
  for (const lock of locks) {
    const lockRM = Number(lock.river_mile);
    if (!Number.isFinite(lockRM)) continue;
    let dist;
    if (heading === "northbound") dist = lockRM - rm;
    else if (heading === "southbound") dist = rm - lockRM;
    else continue;
    if (dist > 0 && dist < bestDist) {
      best = lock;
      bestDist = dist;
    }
  }
  return best ? { lockId: best.id, lock: best, distance: bestDist } : null;
}
