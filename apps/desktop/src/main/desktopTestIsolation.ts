import { existsSync, readFileSync, readdirSync, realpathSync, statSync } from "node:fs";
import path from "node:path";

export interface DesktopTestIsolation {
  backendOrigin: string;
  profileRoot: string;
  rendererDocument: string;
}

export const PRODUCTION_CONNECT_SOURCE = "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000;";

/** Explicit unpackaged test mode; ordinary launches keep their fixed endpoint. */
export function resolveDesktopTestIsolation(
  repositoryRoot: string,
  environ: NodeJS.ProcessEnv = process.env,
  isPackaged = false,
  builtRendererRoot = path.join(repositoryRoot, "apps", "desktop", "dist"),
): DesktopTestIsolation | null {
  const mode = environ.WORKBENCH_DESKTOP_TEST_MODE;
  if (!mode && !environ.WORKBENCH_TEST_BACKEND_ORIGIN && !environ.WORKBENCH_TEST_PROFILE_ROOT && !environ.WORKBENCH_TEST_RENDERER_DOCUMENT) return null;
  if (mode !== "isolated" || isPackaged) throw new Error("Desktop test mode requires an unpackaged isolated launch.");
  const backendOrigin = environ.WORKBENCH_TEST_BACKEND_ORIGIN ?? "";
  const match = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/.exec(backendOrigin);
  const port = Number(match?.[1]);
  if (!match || port > 65535 || port === 8000) throw new Error("Desktop test backend must use an explicit alternate IPv4 loopback port.");
  for (const name of ["WORKBENCH_DATA_ROOT", "WORKBENCH_TEST_PROFILE_ROOT", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"]) {
    requireDesktopTestScratchPath(repositoryRoot, environ[name], name);
  }
  const rendererDocument = requireDesktopTestScratchPath(repositoryRoot, environ.WORKBENCH_TEST_RENDERER_DOCUMENT, "WORKBENCH_TEST_RENDERER_DOCUMENT");
  validateDesktopTestRenderer(builtRendererRoot, rendererDocument, backendOrigin);
  return { backendOrigin, profileRoot: path.resolve(environ.WORKBENCH_TEST_PROFILE_ROOT!), rendererDocument };
}

/** The isolated document can change only the fixed backend CSP; executable assets stay built bytes. */
function validateDesktopTestRenderer(originalRoot: string, rendererDocument: string, backendOrigin: string): void {
  if (path.basename(rendererDocument) !== "index.html" || !existsSync(rendererDocument) || !statSync(rendererDocument).isFile()) {
    throw new Error("Desktop test renderer must be an existing copied index.html.");
  }
  const original = readFileSync(path.join(originalRoot, "index.html"), "utf8");
  if (original.split(PRODUCTION_CONNECT_SOURCE).length !== 2) throw new Error("The built renderer does not have the expected fixed backend CSP.");
  const expected = original.replace(PRODUCTION_CONNECT_SOURCE, `connect-src 'self' ${backendOrigin};`);
  if (readFileSync(rendererDocument, "utf8") !== expected) throw new Error("Desktop test renderer may change only its owned backend CSP.");
  const copiedRoot = path.dirname(rendererDocument);
  const entries = (root: string, relative = ""): string[] => readdirSync(path.join(root, relative), { withFileTypes: true }).flatMap(entry => {
    if (entry.isSymbolicLink()) throw new Error("Desktop test renderer cannot contain redirected assets.");
    const name = path.join(relative, entry.name);
    if (entry.isDirectory()) return entries(root, name);
    if (!entry.isFile()) throw new Error("Desktop test renderer must contain only built files.");
    return [name];
  }).sort();
  const originals = entries(originalRoot);
  const copies = entries(copiedRoot);
  if (JSON.stringify(originals) !== JSON.stringify(copies)) throw new Error("Desktop test renderer must contain exactly the current built assets.");
  for (const relative of originals) {
    if (relative === "index.html") continue;
    if (!readFileSync(path.join(originalRoot, relative)).equals(readFileSync(path.join(copiedRoot, relative)))) {
      throw new Error("Desktop test renderer assets must match the current build.");
    }
  }
}

/** Resolve existing ancestors too, so a junction cannot turn scratch into user data. */
export function requireDesktopTestScratchPath(repositoryRoot: string, value: string | undefined, label: string): string {
  if (!value || !path.isAbsolute(value)) throw new Error(`${label} must be an absolute checkout scratch path.`);
  const scratch = path.resolve(repositoryRoot, ".scratch");
  const target = path.resolve(value);
  const relative = path.relative(scratch, target);
  if (!relative || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`${label} must remain beneath this checkout's root scratch directory.`);
  }
  const actualScratch = realpathSync.native(scratch);
  const expectedScratch = path.join(realpathSync.native(repositoryRoot), ".scratch");
  if (path.relative(expectedScratch, actualScratch)) throw new Error("The checkout scratch directory must not redirect outside the checkout.");
  let ancestor = target;
  const missing: string[] = [];
  while (!existsSync(ancestor)) {
    missing.unshift(path.basename(ancestor));
    const parent = path.dirname(ancestor);
    if (parent === ancestor) throw new Error(`${label} has no existing scratch ancestor.`);
    ancestor = parent;
  }
  const resolved = path.resolve(realpathSync.native(ancestor), ...missing);
  const actualRelative = path.relative(actualScratch, resolved);
  if (!actualRelative || actualRelative === ".." || actualRelative.startsWith(`..${path.sep}`) || path.isAbsolute(actualRelative)) {
    throw new Error(`${label} resolves outside this checkout's root scratch directory.`);
  }
  return target;
}
