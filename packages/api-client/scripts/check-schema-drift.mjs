#!/usr/bin/env node
// Regenerates src/schema.d.ts from openapi.json into a temp file and fails
// if it differs from the committed version - the same drift-check pattern
// scripts/export_openapi.py and scripts/generate_erd.py already use on the
// Python side, applied to the generated TS client (P0-081).

import { execFileSync } from "node:child_process";
import { readFileSync, unlinkSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const committed = path.join(root, "src", "schema.d.ts");
const fresh = path.join(root, "src", "schema.d.ts.fresh");

// node_modules/.bin/openapi-typescript is a POSIX shell shim (not JS) that
// resolves symlinks and then execs the real CLI entry point, so it must be
// run directly (its own shebang picks the interpreter) rather than passed
// as an argument to `node`, which fails trying to parse the shim as JS.
execFileSync(
  path.join(root, "node_modules", ".bin", "openapi-typescript"),
  [path.join(root, "openapi.json"), "-o", fresh],
  { stdio: "inherit" },
);

const committedText = readFileSync(committed, "utf8");
const freshText = readFileSync(fresh, "utf8");
unlinkSync(fresh);

if (committedText !== freshText) {
  console.error(
    "src/schema.d.ts is out of date with openapi.json. Run `pnpm --filter @creatoriqx/api-client run generate` and commit the result.",
  );
  process.exit(1);
}

console.log("src/schema.d.ts matches openapi.json.");
