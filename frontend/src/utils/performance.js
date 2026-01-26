/**
 * Performance utilities for River Watch
 */

/**
 * Creates a throttled version of a function that only executes at most once per interval
 * @param {Function} func - Function to throttle
 * @param {number} limit - Minimum time between calls in ms
 * @returns {Function} Throttled function
 */
export function throttle(func, limit) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

/**
 * Creates a debounced version of a function that only executes after a delay
 * @param {Function} func - Function to debounce
 * @param {number} delay - Delay in ms before execution
 * @returns {Function} Debounced function
 */
export function debounce(func, delay) {
  let timeoutId;
  return function(...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func.apply(this, args), delay);
  };
}

/**
 * Compare two vessel objects for meaningful changes
 * Returns true if the vessel has changed significantly
 * @param {Object} prev - Previous vessel state
 * @param {Object} next - New vessel state
 * @returns {boolean} Whether there's a significant change
 */
export function hasVesselChanged(prev, next) {
  if (!prev || !next) return true;
  
  // Position changed by more than ~10 meters (0.0001 degrees)
  const latDiff = Math.abs((prev.lat || 0) - (next.lat || 0));
  const lonDiff = Math.abs((prev.lon || 0) - (next.lon || 0));
  if (latDiff > 0.0001 || lonDiff > 0.0001) return true;
  
  // Speed changed by more than 0.5 knots
  const speedDiff = Math.abs((prev.speed || 0) - (next.speed || 0));
  if (speedDiff > 0.5) return true;
  
  // Course changed by more than 5 degrees
  const courseDiff = Math.abs((prev.course || 0) - (next.course || 0));
  if (courseDiff > 5) return true;
  
  return false;
}

/**
 * Shallow compare two objects
 * @param {Object} a - First object
 * @param {Object} b - Second object
 * @returns {boolean} Whether objects are equal
 */
export function shallowEqual(a, b) {
  if (a === b) return true;
  if (!a || !b) return false;
  
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  
  if (keysA.length !== keysB.length) return false;
  
  for (const key of keysA) {
    if (a[key] !== b[key]) return false;
  }
  
  return true;
}
