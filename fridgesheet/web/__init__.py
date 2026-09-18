"""The local web app (spec 2026-09-15): the database layer (`db`, `ingest`, `stores`,
`reconcile`) and the server Plan B part 1 puts in front of it -- `server` (one instance per
home), `app` (the FastAPI application), `routes/` and the Jinja2 `templates/`. Part 2 adds
the jobs worker, Settings and Diagnostics."""
