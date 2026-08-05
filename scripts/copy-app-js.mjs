import { cp, mkdir, rm } from "node:fs/promises";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";

export async function copyAppJs() {
  // Keep application modules debuggable; bundle only the dependency-backed Sentry entrypoint.
  await rm("frontend/static/js", { recursive: true, force: true });
  await mkdir("frontend/static/js", { recursive: true });
  await cp("frontend/src/js", "frontend/static/js", {
    recursive: true,
    force: true,
  });
  await build({
    bundle: true,
    entryPoints: ["frontend/src/js/sentry.js"],
    minify: true,
    outfile: "frontend/static/js/sentry.js",
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await copyAppJs();
}
