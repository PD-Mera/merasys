# Changelog

## 0.6.0 — 2026-11-02

- Consolidate code, deployment templates and documentation into the three deployment directories.
- Replace standalone HTML with React 19.3, TypeScript 5.9 and Vite 7.3, built in Docker with Node 22.
- Serve mounted frontend builds through FastAPI; frontend updates require a build and browser reload.
- Allow short passwords and show the saved database URL on the authenticated settings page.
- Manage agent IPs and tokens by row: edit, generate, copy, remove and import JSON.
- Install agents in one command directly from core with URL/server/token arguments, preserving a backup when reconfiguring.
- Adopt Conventional Commits and Semantic Versioning after completed changes.

Validation: TypeScript/Vite Docker build, Python and Bash syntax checks, Compose validation and deployment HTTP checks. No tests run, as requested.
