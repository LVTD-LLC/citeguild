import { cp, mkdir, rm } from "node:fs/promises";
import { pathToFileURL } from "node:url";

export async function copyAppJs() {
  // Keep modules debuggable and close to Django staticfiles instead of bundling/minifying them.
  await rm("frontend/static/js", { recursive: true, force: true });
  await mkdir("frontend/static/js", { recursive: true });
  await cp("frontend/src/js", "frontend/static/js", {
    recursive: true,
    force: true,
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await copyAppJs();
}
