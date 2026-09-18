# Glossary

Use these locked terms in issues, pull requests, and user-facing copy.

| Wrong / loose | Locked |
| --- | --- |
| thtaib / the app (product name) | Local AI Workbench |
| just add the folders | Windows-first scaffold (OQ-001) |
| make it run AI | Out of scope this milestone |
| host Vite / second server | One FastAPI backend + one Electron desktop |
| local verification host | Where UAT runs (David-PC) — not a second product mode |

## Product and layout

**Local AI Workbench** is the product name. The GitHub repository may be named `thtaib`; that is not the product name.

**Windows-first scaffold (OQ-001)** is the supported application layout and toolchain: `apps/backend`, `apps/desktop`, root `specs/`, `scripts/`, and `tests/specs/`.

**workbench_backend** is the Python import package under `apps/backend/src/workbench_backend`.

**Repository-map binding** is a real path recorded in `specs/repository-map.json`. Unbound entries stay `null` until their `required_before` trigger.

**Provisional localhost HTTP** is loopback smoke for the FastAPI process. It does not close [OQ-002](../specs/open-questions.md#oq-002) and is not a trust model.

**Docker Compose stub** is `infra/docker-compose.yml` with no product services. Compose is reserved for later container services.

**electron-builder (NSIS)** is the Windows packaging owner on the desktop app. A working package script may exist before an installer is required as evidence.

**David-PC** is the local verification host for UAT (`D:\CodeProjects\thtaib`). Cloud or CI checks do not replace that label.
