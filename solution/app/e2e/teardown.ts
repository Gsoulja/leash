import { compose } from "./stack";

export default function teardown() {
  if (process.env.LEASH_E2E_REUSE || process.env.LEASH_E2E_KEEP) return;
  compose("down", "-v", "--remove-orphans");
}
