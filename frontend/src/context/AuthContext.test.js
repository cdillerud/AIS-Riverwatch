import { readJson, SERVER_UNAVAILABLE } from "./AuthContext";

const res = (body, type) => ({
  headers: { get: (k) => (k.toLowerCase() === "content-type" ? type : null) },
  json: async () => JSON.parse(body),
});

test("JSON replies are parsed", async () => {
  await expect(readJson(res('{"user":{"id":1}}', "application/json"))).resolves.toEqual({ user: { id: 1 } });
});

test("an HTML error page from static hosting gives a readable message", async () => {
  await expect(readJson(res("<!DOCTYPE html><html>404</html>", "text/html"))).rejects.toThrow(SERVER_UNAVAILABLE);
});

test("broken JSON gives the same message", async () => {
  await expect(readJson(res("{oops", "application/json"))).rejects.toThrow(SERVER_UNAVAILABLE);
});
