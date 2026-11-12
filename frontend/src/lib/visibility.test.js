import { whenVisible, onVisible } from "./visibility";

function setVisibility(v) {
  Object.defineProperty(document, "visibilityState", { value: v, configurable: true });
}

test("skips work while hidden and refreshes when visible again", () => {
  const fn = jest.fn();
  const tick = whenVisible(fn);
  setVisibility("hidden");
  tick();
  expect(fn).not.toHaveBeenCalled();
  const back = jest.fn();
  const off = onVisible(back);
  setVisibility("visible");
  document.dispatchEvent(new Event("visibilitychange"));
  expect(back).toHaveBeenCalledTimes(1);
  tick();
  expect(fn).toHaveBeenCalledTimes(1);
  off();
});
