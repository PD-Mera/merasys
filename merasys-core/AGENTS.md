# UI-only delegation

When assigned UI work, read `UI-HANDOFF.md` first. The delegated agent may edit only components and styles in `frontend/src/`. Do not create legacy HTML files or duplicate source at the repository root.

UI work must preserve monitoring semantics, counts, states, polling, authentication and the API contract. Do not edit Python, backend logic, DB, alerts, Sheet integration, agents, Docker files, dependencies, configuration or secrets to accomplish a UI task.

Do not run tests, install test dependencies or create test environments on this machine. Do not deploy without explicit user authorization. Report the source files and frontend build command from `FRONTEND.md`. UI-only releases need a frontend build and browser reload after the initial React migration, without restarting the backend.

These UI scope restrictions apply to UI-only assignments; they do not authorize unrelated changes or override a later explicit user assignment.
