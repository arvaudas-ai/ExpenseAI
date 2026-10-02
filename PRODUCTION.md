# ExpenseAI Production Configuration

ExpenseAI keeps its FastAPI, SQLite, and vanilla JavaScript architecture. Configure deployment values through environment variables rather than source code.

## Required configuration

Copy `.env.example` to `.env` for local setup, or provide equivalent environment variables through the process manager:

- `APP_NAME`: application name, normally `ExpenseAI`.
- `DATABASE_URL`: SQLAlchemy database URL. The default is the local SQLite file.
- `ENVIRONMENT`: use `development` locally and `production` for deployment.
- `JWT_SECRET_KEY`: a random secret of at least 32 characters. Never commit it or place it in `.env.example`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: positive token lifetime in minutes, no more than 1440.
- `CORS_ALLOWED_ORIGINS`: comma-separated exact browser origins, such as `https://app.example.com`. Leave empty for same-origin development.
- `SERVER_HOST`: bind address for the production launcher. Keep `127.0.0.1` when a reverse proxy is on the same host.
- `SERVER_PORT`: listening port for the production launcher.
- `TRUSTED_PROXY_IPS`: comma-separated IPs allowed to provide forwarded headers. Keep this limited to the actual reverse proxy network.
- `AI_PROVIDER`: `local` for the built-in deterministic assistant, or `openai_compatible` for an optional compatible chat-completions provider.
- `AI_API_KEY`: optional provider credential. Keep it server-side and never expose it to browser code.
- `AI_MODEL`: model name used by the optional external provider.
- `AI_BASE_URL`: base URL for the optional OpenAI-compatible provider.
- `AI_TIMEOUT_SECONDS`: bounded external-provider request timeout.

Generate a secret with:

```text
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

In production, the application refuses to start when `JWT_SECRET_KEY` is missing or shorter than 32 characters. Development uses an ephemeral process-local secret when one is not supplied; this is suitable only for local testing because tokens become invalid after restart.

## Development

Keep `ENVIRONMENT=development` and run the application with the project virtual environment:

```text
.venv\\Scripts\\uvicorn.exe app.main:app --reload
```

The application is same-origin by default. If a separate local frontend is used, configure `CORS_ALLOWED_ORIGINS` with exact origins rather than using a wildcard.

## Production process

Set all environment variables through the deployment platform or process manager, then run the production launcher without development reload:

```text
.venv\\Scripts\\python.exe scripts\\run_production.py
```

The launcher reads `SERVER_HOST`, `SERVER_PORT`, and `TRUSTED_PROXY_IPS`, and always sets `reload=False`. Terminate TLS at a trusted reverse proxy or load balancer and forward only the required public routes. `Strict-Transport-Security` is emitted when `ENVIRONMENT=production`, so production traffic must be served over HTTPS.

For a small same-host deployment, bind the application to `127.0.0.1` and let the reverse proxy handle the public interface. Do not set `TRUSTED_PROXY_IPS=*` unless every network path to the application is controlled.

## SQLite limitations

SQLite is appropriate for a small single-process deployment and local development. It uses a file, has limited write concurrency, and is not a good fit for multiple application workers or high-throughput workloads. Back up `expenseai.db` using an application-aware backup process, and plan a managed database migration before scaling horizontally. Do not delete or recreate the existing database as part of routine deployment.

## Security notes

- Authentication uses signed JWTs with required subject, issuer, issued-at, and expiration claims.
- Protected resources filter by the authenticated user ID.
- Passwords are stored as PBKDF2-derived hashes, never plaintext.
- The application adds content-type, frame, referrer, permissions, and production transport security headers.
- Review logs and reverse-proxy configuration separately; do not expose stack traces or secret environment values to clients.

## Health check

The lightweight public endpoint `GET /api/health` returns only the service status and name. Use it for a reverse-proxy or process-manager health check; it does not expose database contents, environment variables, or credentials.

## Public deployment checklist

- [ ] Strong `JWT_SECRET_KEY` configured outside source control
- [ ] `ENVIRONMENT=production` enabled
- [ ] Exact HTTPS origins configured in `CORS_ALLOWED_ORIGINS`
- [ ] HTTPS and redirect policy configured at the reverse proxy
- [ ] Database strategy selected and `DATABASE_URL` configured
- [ ] Automated backups for `expenseai.db` configured for SQLite deployments
- [ ] Monitoring and log collection configured without secrets
- [ ] Secure process manager configured with restart and resource policies
- [ ] Domain and DNS configured
- [ ] `GET /api/health` verified through the proxy
- [ ] `TRUSTED_PROXY_IPS` restricted to the proxy network

ExpenseAI is deployment-prepared but is not publicly deployed by this project step. Complete the checklist and perform a production smoke test in a controlled environment before opening public traffic.

## Financial assistant

The authenticated `POST /api/assistant/chat` endpoint provides spending analysis using only the current user's normalized totals, categories, payment methods, and limited expense summaries. It never accepts a `user_id` from the browser and does not send passwords, hashes, tokens, database credentials, or raw database objects to a provider.

The default `AI_PROVIDER=local` mode answers supported spending questions from calculated data and requires no external service or API key. To use an OpenAI-compatible provider, set `AI_PROVIDER=openai_compatible`, `AI_API_KEY`, `AI_MODEL`, and `AI_BASE_URL` through the private deployment environment. Tests mock the provider and never call an external AI service. The assistant is an analytics and education feature, not financial advice.
