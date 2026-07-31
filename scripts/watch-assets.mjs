import { spawn } from "node:child_process";
import { watch } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { copyAppJs } from "./copy-app-js.mjs";

const cssInput = "frontend/src/styles/index.css";
const cssOutput = "frontend/static/css/app.css";
const readyFile = "frontend/static/.assets-ready";
const tailwindArgs = ["-i", cssInput, "-o", cssOutput];

function runTailwind(args) {
  return new Promise((resolve, reject) => {
    const child = spawn("tailwindcss", args, {
      shell: process.platform === "win32",
      stdio: "inherit",
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`tailwindcss exited with code ${code}`));
    });
  });
}

let copyingJs = false;
let pendingJsCopy = false;

async function copyJsWithQueue() {
  if (copyingJs) {
    pendingJsCopy = true;
    return;
  }

  copyingJs = true;
  try {
    do {
      pendingJsCopy = false;
      await copyAppJs();
    } while (pendingJsCopy);
  } finally {
    copyingJs = false;
  }
}

await copyJsWithQueue();
await runTailwind(tailwindArgs);
await mkdir(dirname(readyFile), { recursive: true });
await writeFile(readyFile, `${new Date().toISOString()}\n`);

const jsWatcher = watch("frontend/src/js", { recursive: true }, (_eventType, filename) => {
  if (!filename) {
    return;
  }
  console.log(`JS changed: ${filename}`);
  void copyJsWithQueue().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
});

const tailwindWatcher = spawn("tailwindcss", [...tailwindArgs, "--watch"], {
  shell: process.platform === "win32",
  stdio: "inherit",
});

function stop() {
  jsWatcher.close();
  tailwindWatcher.kill("SIGTERM");
}

process.on("SIGINT", () => {
  stop();
  process.exit(130);
});

process.on("SIGTERM", () => {
  stop();
  process.exit(143);
});

tailwindWatcher.on("error", (error) => {
  jsWatcher.close();
  throw error;
});

tailwindWatcher.on("exit", (code) => {
  jsWatcher.close();
  process.exit(code ?? 0);
});
