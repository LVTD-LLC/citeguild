import { copyFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const vendorFiles = [
  {
    source: "node_modules/htmx.org/dist/htmx.min.js",
    destination: "frontend/static/vendors/js/htmx.min.js",
  },
  {
    source: "node_modules/alpinejs/dist/cdn.min.js",
    destination: "frontend/static/vendors/js/alpine.min.js",
  },
];

for (const file of vendorFiles) {
  await mkdir(dirname(file.destination), { recursive: true });
  await copyFile(file.source, file.destination);
}
