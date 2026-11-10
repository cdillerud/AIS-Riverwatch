// Persistent, unobtrusive safety notice shown at the bottom of every page.
export const DISCLAIMER_TEXT =
  "Not for navigation. Positions and lock times are estimates; follow lockmaster instructions and the Inland Navigation Rules.";

export default function Disclaimer() {
  return (
    <footer
      className="bg-[#020617] px-4 py-2 text-center text-[10px] leading-snug text-slate-600"
      data-testid="nav-disclaimer"
    >
      {DISCLAIMER_TEXT}
    </footer>
  );
}
