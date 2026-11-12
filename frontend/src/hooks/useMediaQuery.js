import { useEffect, useState } from "react";

// true while the CSS media query matches. The dashboard renders only the
// layout in use: hiding the other with CSS still mounted it, so a phone ran
// the desktop map and both trees' pollers (two Trip Plans, two planners).
export default function useMediaQuery(query) {
  const get = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : true);
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mql = window.matchMedia(query);
    const on = () => setMatches(mql.matches);
    on();
    mql.addEventListener ? mql.addEventListener("change", on) : mql.addListener(on);
    return () => (mql.removeEventListener ? mql.removeEventListener("change", on) : mql.removeListener(on));
  }, [query]);
  return matches;
}
