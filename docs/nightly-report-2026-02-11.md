# Nightly maintenance failure report (2026-02-11 00:00 ET)

## What ran
1. `git fetch --all --prune`
2. `git checkout main`
3. `git pull --ff-only`
4. `python3 -m venv .venv` (created if missing)
5. `.venv/bin/pip install -r requirements.txt`
6. `bash scripts/demo.sh`

## Git status
- Branch: `main`
- Result: already up to date with `origin/main`

## Failure 1: dependency install
### Command
`source .venv/bin/activate && python -m pip install -r requirements.txt`

### Key log excerpt
```
Error: pg_config executable not found.
pg_config is required to build psycopg2 from source.
ERROR: Failed to build 'psycopg2-binary' when getting requirements to build wheel
```

### Likely cause
- Host Python is `3.14.3`; wheels for pinned deps are not available, so pip falls back to source builds.
- Source build for `psycopg2-binary==2.9.9` requires PostgreSQL dev tooling (`pg_config`), which is not installed.

## Failure 2: demo run
### Command
`bash scripts/demo.sh`

### Key log excerpt
```
scripts/demo.sh: line 21: docker: command not found
```

### Likely cause
- `scripts/demo.sh` depends on Docker Compose for Postgres startup.
- Docker CLI/daemon is not installed or not in PATH on this host.

## Suggested low-risk fix steps
1. **Pin a supported Python runtime for this project** (likely 3.11/3.12) and install using that interpreter.
2. **Install Docker Desktop / Docker Engine** and verify `docker compose` works.
3. If keeping current Python version, install PostgreSQL dev tools so `pg_config` is available (or move to deps that provide wheels for current Python).
4. Re-run:
   - `pip install -r requirements.txt`
   - `bash scripts/demo.sh`

## Notes
- No product code changes were made.
- Milestone implementation was intentionally skipped because baseline demo/health is currently red.
