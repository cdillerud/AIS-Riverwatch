import { act } from "react";
import { createRoot } from "react-dom/client";
import LockClosureLimits from "./LockClosureLimits";

function render(limits) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => root.render(<LockClosureLimits limits={limits} />));
  return { el, root };
}

test("shows computed comparisons, highlighting ones near the limit, and the source", () => {
  const { el, root } = render({
    district: "USACE St. Paul District",
    source_url: "https://www.mvp.usace.army.mil/Missions/Navigation/Locks-Dams/",
    checked: "2026-11-12",
    comparisons: [
      { kind: "flow", limit_kind: "closed", near: true, gauge: "USACE CWMS LockDam_02.Flow-Out",
        observed_at: "2026-11-13T02:15:00+00:00",
        text: "River at 82% of the flow that closes this lock (116,000 cfs) - rising" },
      { kind: "pool", limit_kind: "closed", near: false, gauge: "USACE CWMS LockDam_02.Elev",
        text: "Pool at 686.5 ft, 5.5 ft below the level that closes this lock (692.0 ft) - steady" },
    ],
    references: ["Outdraft warning from 31,000 cfs, dam gates pulled at 61,000 cfs"],
  });
  const lines = el.querySelectorAll('[data-testid="lock-limit-comparison"]');
  expect(lines).toHaveLength(2);
  expect(lines[0].textContent).toBe("River at 82% of the flow that closes this lock (116,000 cfs) - rising");
  expect(lines[0].className).toContain("amber");
  expect(lines[1].className).not.toContain("amber");
  expect(el.querySelector('[data-testid="lock-limit-reference"]').textContent).toContain("Outdraft warning");
  expect(el.querySelector("a").getAttribute("href")).toBe("https://www.mvp.usace.army.mil/Missions/Navigation/Locks-Dams/");
  act(() => root.unmount());
});

test("reference-only limits render without a comparison", () => {
  const { el, root } = render({
    district: "USACE Rock Island District", source_url: "https://www.mvr.usace.army.mil/x", checked: "2026-11-12",
    comparisons: [],
    references: ["Closes to navigation at 21.2 ft on the tailwater gauge (USACE Rock Island District)"],
  });
  expect(el.querySelectorAll('[data-testid="lock-limit-comparison"]')).toHaveLength(0);
  expect(el.textContent).toContain("Closes to navigation at 21.2 ft on the tailwater gauge");
  expect(el.textContent).not.toContain("current readings");
  act(() => root.unmount());
});

test("renders nothing without limit data", () => {
  const { el, root } = render(undefined);
  expect(el.innerHTML).toBe("");
  act(() => root.unmount());
});
