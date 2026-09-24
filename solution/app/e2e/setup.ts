import { compose } from "./stack";

export default function setup() {
  if (process.env.LEASH_E2E_REUSE) return;  // a stack already started by hand
  compose("down", "-v", "--remove-orphans");  // a fresh database and fake every time
  compose("up", "-d", "--build", "--wait");
}
