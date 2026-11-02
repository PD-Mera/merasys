# Workspace instructions

- Do not run tests on this machine. This is an explicit user preference.
- Do not install test dependencies or recreate temporary test environments here.
- Preserve the three deployment folders and user configuration when cleaning temporary files.
- For UI-only delegation, read `merasys-core/UI-HANDOFF.md`. Only components and styles in `merasys-core/frontend/src/` may be edited; preserve API and monitoring semantics and do not modify backend or deployment configuration for a UI task.

- After completing each user-requested change, commit the finished work. Use Conventional Commits (`feat`, `fix`, `refactor`, `docs`, `chore`) and Semantic Versioning; keep active package versions and Docker image tags aligned. Never commit user secrets, state, database data, node_modules or generated dist. Do not push or create release tags unless requested.
