// node --test ops/site-worker/test   (ci.yml). The cases live in cases.mjs so the browser harness runs the same ones.
import test from "node:test";
import assert from "node:assert/strict";
import { runCases } from "./cases.mjs";

test("the Worker's gate and /api/state", async () => {
  const r = await runCases();
  for (const c of r.all) console.log((c.ok ? "  ok  " : "  FAIL") + " " + c.msg);
  assert.deepEqual(r.failed.map(f => f.msg), [], "failed cases");
  assert.ok(r.passed >= 30, `only ${r.passed} cases ran`);
});
