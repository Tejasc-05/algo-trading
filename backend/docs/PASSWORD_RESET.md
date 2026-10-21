# Password reset

Login and signup use email/password only. Forgot Password requests a reset email;
the email opens `/reset-password#token=...`. The page removes the fragment from
the address bar after capturing it in memory and asks for the new password twice.
It does not automatically log the user in.

## SMTP setup

Configure backend `.env` (never frontend variables or committed secrets):

```dotenv
PASSWORD_RESET_FRONTEND_URL=https://your-frontend.example
PASSWORD_RESET_EXPIRE_MINUTES=30
SMTP_HOST=your-provider-smtp-host
SMTP_PORT=587
SMTP_USERNAME=your-provider-username
SMTP_PASSWORD=your-provider-password
SMTP_FROM_EMAIL=your-verified-sender@example.com
SMTP_STARTTLS=true
SMTP_SSL=false
```

For implicit TLS use port 465, `SMTP_SSL=true`, `SMTP_STARTTLS=false`.
Production requires HTTPS for the frontend origin and encrypted SMTP transport.
The frontend setting must be an origin, without path, credentials, query or
fragment. The server never uses an untrusted request Host header to build links.
Without configured delivery both known and unknown addresses receive the same
503 configuration error; the application does not pretend an email was sent.

For a local Docker mailbox (no provider keys or real external emails), add:

```dotenv
PASSWORD_RESET_FRONTEND_URL=http://localhost:5173
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_FROM_EMAIL=noreply@example.com
SMTP_STARTTLS=false
SMTP_SSL=false
SMTP_USERNAME=
SMTP_PASSWORD=
```

Then run from `backend/`:

```sh
docker compose --profile dev-mail up -d mailpit api
```

Read captured email at http://localhost:8025. SMTP is reachable only inside the
Compose network; the mailbox UI port binds to localhost. This is a development
mailbox, not delivery to users' inboxes. Set `ENVIRONMENT=development` for local
HTTP. API startup runs migration `0009_password_reset`. Restart/recreate the API
after changing its environment; example variables alone do not configure it.

## Guarantees and limits

- Request: `POST /api/auth/forgot-password` with `email`, returning a uniform 202
  message regardless of account existence/activity. Email lookup and delivery
  happen after the response in a background task.
- Rate limits: five request attempts per IP per 15 minutes, three per normalized
  email per hour (Redis keys use a digest), and ten completion attempts per IP
  per 15 minutes. Addresses aren't locked or changed by requesting recovery.
- Tokens: cryptographically random 32-byte secrets; only SHA-256 digests, user
  id, authentication version, expiry and consumption timestamps are persisted.
  Defaults to 30 minutes; configured expiry is bounded to 5–60 minutes.
- Completion: `POST /api/auth/reset-password` with `token`, `password` and
  `confirm_password`. Password policy matches signup (minimum 8 characters and
  maximum 72 UTF-8 bytes for bcrypt). Invalid, expired, inactive, superseded and
  consumed links return the same error.
- User row locks serialize reset issuance/completion in PostgreSQL. Completion
  changes the password hash, increments the authentication version and consumes
  every outstanding link in one transaction. Strategies, balances, trades,
  exchange connections and user identity are retained.
- New JWTs carry the authentication version. Legacy JWTs without it work only
  for users still on version zero; any completed reset invalidates them. Existing
  WebSockets reauthenticate before forwarding an event and at 30-second idle
  intervals; a reset event prompts closure through Redis. Revoked sockets close
  with 1008, and the frontend returns to login.
- Reset and confirmation emails never contain passwords. Raw tokens, SMTP
  errors/credentials and email bodies are not logged or returned by APIs.
- Delivery failures revoke the undelivered token and log a redacted operational
  warning. The original generic response cannot indicate account-specific mail
  failure. Already valid links remain until expiry or successful completion.
- BackgroundTasks is not a durable delivery queue: process interruption can
  lose a pending email. Operators must monitor SMTP and allow users to retry;
  a durable outbox/worker is a future deployment improvement. SMTP acceptance
  does not guarantee inbox placement. Expired rows remain unusable; schedule
  retention cleanup in a production database.

Validation covers success, reuse/expiry, old-password/session rejection,
retained strategies, all-link invalidation, unknown/inactive users, unconfigured
and failing delivery, matching passwords, byte limits, rate limits and revoked
WebSocket forwarding. SQLite tests do not prove PostgreSQL concurrency behavior.
Real inbox delivery needs operator SMTP credentials and a verified sender.

Reference: [OWASP account recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).
