// LEASH-151: stamp the built bundle with what it was built from, so the API can refuse to serve a
// bundle that is not the one this image was built with (an accidentally mounted stale volume).
//
//   revision  — the source revision, from APP_REVISION (the Docker build arg / CI commit SHA)
//   bundle    — a content hash over every other file in dist/, so two builds of the same source that
//               produced different assets are still distinguishable
//   built_at  — for a human reading a rehearsal log
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";

const DIST = "dist";
const STAMP = "build.json";

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : [path];
  });
}

const assets = files(DIST)
  .filter((path) => relative(DIST, path) !== STAMP)
  .sort();
if (assets.length === 0) throw new Error(`${DIST}/ is empty; nothing to stamp`);

const hash = createHash("sha256");
for (const path of assets) {
  // The path is part of the identity: a renamed asset is a different bundle even with the same bytes.
  hash.update(relative(DIST, path).split(sep).join("/"));
  hash.update(readFileSync(path));
}

const stamp = {
  revision: process.env.APP_REVISION || "unknown",
  bundle: hash.digest("hex").slice(0, 16),
  built_at: new Date().toISOString(),
  files: assets.length,
  bytes: assets.reduce((total, path) => total + statSync(path).size, 0),
};
writeFileSync(join(DIST, STAMP), JSON.stringify(stamp, null, 2) + "\n");
console.log(`stamped ${DIST}/${STAMP}: revision ${stamp.revision}, bundle ${stamp.bundle}, ${stamp.files} files`);
