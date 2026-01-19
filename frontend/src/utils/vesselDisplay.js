/**
 * Get the display name for a vessel based on user settings
 * @param {Object} vessel - The vessel object
 * @param {boolean} showNames - Whether to show names (true) or MMSIs (false)
 * @returns {string} The display name
 */
export function getVesselDisplayName(vessel, showNames = true) {
  if (!vessel) return 'Unknown';
  
  if (showNames && vessel.name) {
    return vessel.name;
  }
  
  return vessel.mmsi || 'Unknown';
}

/**
 * Get a short display name for a vessel (for compact displays)
 * @param {Object} vessel - The vessel object
 * @param {boolean} showNames - Whether to show names (true) or MMSIs (false)
 * @param {number} maxLength - Maximum length before truncating
 * @returns {string} The display name
 */
export function getVesselShortName(vessel, showNames = true, maxLength = 15) {
  const name = getVesselDisplayName(vessel, showNames);
  if (name.length > maxLength) {
    return name.substring(0, maxLength - 2) + '..';
  }
  return name;
}
