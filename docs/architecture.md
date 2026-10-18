# System Architecture and High-Level Design

This describes the intended platform design. It is a guide, not a claim that all features exist: the current scaffold has a FastAPI health route and a React/Vite frontend. Ticketing, authentication, persistence, and AI workflows remain planned work.

## 1. Goals and scope

The platform will let customers open and follow support tickets, let agents manage tickets and conversations, and let administrators manage users and support operations. A later phase can add knowledge search and AI assisted replies, classification, summaries, and escalation safeguards.

Start as a **modular monolith**: one FastAPI application and one PostgreSQL database, with feature code grouped by domain. This keeps development and database transactions simple while preserving boundaries that can be separated later if scale or team ownership calls for it. AI is a future integration behind a service interface, not part of the initial setup.

Initial product scope: versioned REST/JSON API, React browser app, PostgreSQL persistence, authentication and role/resource checks, ticket and conversation workflows, migrations after schema review, and automated tests as features are implemented. AI provider selection, AI SDKs, database tables, and migrations are intentionally deferred.

## 2. High-level component diagram

![Compact platform architecture diagram](architecture-overview.svg)

If the SVG preview is unavailable, the same request path is:

```text
Browser (React) -> FastAPI -> Auth -> Domain service -> Repository
                                                -> SQLAlchemy -> Psycopg -> PostgreSQL
                                  `-> future AI service -> Knowledge search / AI provider
```

The SVG is a standalone vector file, so it stays sharp when zoomed. Open [architecture-overview.svg](architecture-overview.svg) directly if the document viewer constrains the inline image size.

## 3. Components and why they are used

| Component | What it does | Why it is needed |
|---|---|---|
| React | Renders screens and manages local UI state. | Reusable interactive customer and staff screens. |
| Vite | Runs the frontend development server and bundles static assets. | Fast local feedback and a production build. |
| Tailwind CSS | Styles components with utility classes. | Consistent styling without a large custom CSS framework. |
| ESLint | Finds common JavaScript and React mistakes. | Keeps frontend code consistent as it grows. |
| FastAPI | Routes HTTP requests to typed Python handlers and publishes OpenAPI docs. | Request handling, dependency injection, and API documentation. |
| Pydantic | Validates incoming/outgoing data and application settings. | Defines API contracts separately from database records. |
| Domain services | Perform use cases such as creating or assigning a ticket. | Keeps business rules out of routes and SQL queries. |
| Repositories | Encapsulate domain-specific database reads/writes. | Keeps query details out of the use-case logic. |
| SQLAlchemy 2.x | Maps Python model classes to tables and manages sessions/transactions. | Provides a consistent ORM and query layer. |
| Psycopg 3 | Python DBAPI driver that speaks PostgreSQL's protocol. | It is the connector used by SQLAlchemy to connect to a PostgreSQL server; it is not the server itself. |
| PostgreSQL | Stores users, tickets, messages, assignments, and related records. | Relational constraints and transactions fit linked support records. |
| Alembic | Stores reviewed schema changes as versioned migration scripts. | Repeats database changes consistently across environments. |
| PyJWT | Signs and verifies access tokens. | Supports authenticated API requests using signed tokens. |
| pwdlib + Argon2 | Hashes and verifies passwords. | Stores one-way password hashes, not recoverable passwords. |
| HTTPX | Calls external HTTP services in future integrations. | Testable client for an eventual AI provider or other API. |
| pytest / pytest-asyncio | Runs unit and API integration checks. | Protects behavior and authorization rules from regressions. |
| Ruff | Lints/formats Python code. | Fast checks for style and common errors. |

### How Psycopg connects the application to PostgreSQL

The planned synchronous SQLAlchemy URL looks like:

```text
postgresql+psycopg://username:password@host:5432/database_name
```

`postgresql+psycopg` selects SQLAlchemy's PostgreSQL dialect and Psycopg 3 driver. SQLAlchemy turns ORM operations into SQL; Psycopg sends SQL and parameters to PostgreSQL and returns rows. `psycopg[binary]` supplies binary support so a separate client library is generally unnecessary for local Python development. It does **not** install or run the PostgreSQL database server. Credentials belong in environment variables, never source control.

Use synchronous SQLAlchemy sessions with Psycopg's synchronous driver initially. FastAPI can run regular `def` handlers in its worker pool. If asynchronous DB I/O is later needed, deliberately adopt SQLAlchemy's async engine and Psycopg async connection mode rather than mixing patterns.

## 4. Backend structure and request flow

```mermaid
sequenceDiagram
  participant UI as React UI
  participant R as FastAPI router
  participant P as Pydantic schema
  participant S as Domain service
  participant Repo as Repository
  participant ORM as SQLAlchemy Session
  participant D as Psycopg
  participant DB as PostgreSQL
  UI->>R: JSON request + access token
  R->>P: Parse and validate input
  R->>R: Authenticate and check role/resource access
  R->>S: Call one use-case method
  S->>Repo: Read/write domain data
  Repo->>ORM: Build ORM query
  ORM->>D: SQL and parameters
  D->>DB: PostgreSQL protocol
  DB-->>D: Result rows / transaction result
  D-->>ORM: Python values
  ORM-->>Repo: ORM objects
  Repo-->>S: Domain data
  S-->>R: Result or domain error
  R-->>UI: Status code + response JSON
```

1. A **router** declares the URL, HTTP method, dependencies, and response schema. It should not contain multi-step business rules or SQL.
2. A **Pydantic request schema** validates types and input constraints. Validation is not authorization.
3. An **authentication dependency** verifies the JWT and supplies the current user.
4. **Authorization** checks both role and record ownership/assignment. Knowing a ticket ID does not grant access.
5. A **service** runs the use case, applies business rules, and defines a transaction for multi-record changes.
6. A **repository** queries and persists through a supplied SQLAlchemy session. It does not commit.
7. A **response schema** exposes approved fields only; never password hashes, tokens, or internal persistence details.
8. Domain errors become stable HTTP errors. Unexpected errors are logged safely and do not reveal stack traces or secrets.

Use one request-scoped SQLAlchemy `Session`, always close it, and let the service own a transaction such as `with session.begin():`. This makes a ticket update and its history event atomic. Repositories can `flush()` to get generated IDs but should not `commit()` independently.

## 5. Feature boundaries and data concepts

Each module under `backend/app/modules/` may contain `router.py`, `schemas.py`, `models.py`, `repository.py`, and `service.py` as needed. Small modules can omit unneeded files. Shared infrastructure belongs in `core/` or `db/`; avoid one giant global service/repository.

- **Users/auth:** identity ID, normalized email, password hash, role, active flag, and timestamps. Customer, agent, and admin are initial role candidates. Never store raw passwords.
- **Customers:** customer profile associated with a user; customers normally see their own tickets.
- **Agents:** staff profile, team/availability if required, and assignment eligibility.
- **Tickets:** customer, subject, description, status, priority, assignee, timestamps. Use constrained enums and record status/assignment changes.
- **Conversations:** messages/comments linked to a ticket and author. Explicitly distinguish public replies from internal staff notes so internal notes cannot leak to customers.
- **History/audit:** status and assignment events with actor/time. Decide required retention and detail before schema design.
- **Knowledge base (later):** approved articles and traceable chunks used by retrieval, each with source/version metadata.

Use `/api/v1` as the API prefix. Planned endpoint groups include `/auth`, `/customers`, `/agents`, `/tickets`, `/tickets/{id}/comments`, and later `/knowledge`. List endpoints need pagination, stable ordering, and access-scoped filters. Return explicit Pydantic responses. Use consistent `401` (unauthenticated), `403` (not permitted), `404` (missing or intentionally hidden), and `422` (invalid input) behavior.

### Response structure

Return a resource object directly for a single successful resource, a paginated object for lists, and one consistent envelope for errors. Avoid wrapping every success in an extra `data` object; the endpoint's declared response schema already identifies the resource.

Example ticket response (`TicketRead`, `201 Created`):

```json
{
  "id": "ticket_123",
  "subject": "Cannot access my account",
  "description": "Password reset does not arrive.",
  "status": "open",
  "priority": "normal",
  "customer_id": "user_456",
  "assigned_agent_id": null,
  "created_at": "2026-10-18T12:30:00Z",
  "updated_at": "2026-10-18T12:30:00Z"
}
```

Example paginated collection (`TicketListResponse`, `200 OK`):

```json
{
  "items": [
    {
      "id": "ticket_123",
      "subject": "Cannot access my account",
      "description": "Password reset does not arrive.",
      "status": "open",
      "priority": "normal",
      "customer_id": "user_456",
      "assigned_agent_id": null,
      "created_at": "2026-10-18T12:30:00Z",
      "updated_at": "2026-10-18T12:30:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "has_next": false
}
```

Example login response (`TokenResponse`, `200 OK`):

```json
{
  "access_token": "<signed-token>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Example error response (for example, `422 Unprocessable Entity`):

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request contains invalid fields.",
    "details": [
      { "field": "subject", "message": "Field is required." }
    ],
    "request_id": "req_abc123"
  }
}
```

Use the same error shape for authentication, permission, not-found, conflict, and unexpected server errors. `details` can be an empty list when no field-level details are safe to return. Do not include stack traces, SQL, password values, tokens, or internal notes. A `204 No Content` response has no JSON body. Internal conversation notes must be filtered before constructing any customer-facing response schema.

## 6. Main workflows

### Customer opens a ticket

```mermaid
sequenceDiagram
  actor Customer
  participant UI as React
  participant API as FastAPI
  participant S as TicketService
  participant DB as PostgreSQL
  Customer->>UI: Enter subject and description
  UI->>API: POST /api/v1/tickets
  API->>API: Validate token and customer access
  API->>S: create_ticket(actor, input)
  S->>S: Apply initial status and field rules
  S->>DB: Save ticket and initial event in one transaction
  DB-->>S: Created record and IDs
  S-->>API: Ticket result
  API-->>UI: 201 + TicketRead JSON
  UI-->>Customer: Show ticket detail
```

### Agent replies and updates status

1. The agent UI requests a ticket with its access token.
2. The API verifies agent role and ticket access.
3. The agent posts a public reply or explicitly chooses an internal note.
4. The conversation service stores author, text, visibility, and timestamp.
5. Status changes go through `TicketService`, which validates the transition and records history in the same transaction.
6. Timeline responses omit internal notes for customers.

### Future AI-assisted response

1. An authorized workflow requests a draft; AI does not silently act on every message.
2. Knowledge search retrieves relevant approved article chunks and sources.
3. A provider adapter sends only necessary conversation context and retrieved text through HTTPX, with timeout limits.
4. The response is validated, safety checked, and associated with source/usage metadata.
5. Initially the output is a draft for an agent to review. Low confidence, safety-sensitive, or unsupported cases escalate to a human.
6. Provider failure or no relevant retrieval falls back to normal support. AI never bypasses ticket authorization or receives internal notes by default.

## 7. Frontend organization

As screens are added, keep `src/pages/` for route views, `src/components/` for reusable controls, `src/api/` for HTTP helpers, `src/auth/` for UI authentication state, and `src/routes/` for navigation/guards. A central API client attaches tokens and handles JSON/errors; components should not each implement transport. React is presentation, while the API remains authoritative for ticket state and permissions. Do not place server secrets or AI provider keys in browser environment variables.

## 8. Security and operations

- Load configuration with Pydantic Settings. `.env.example` contains placeholders only; `.env` stays ignored.
- Use TLS in deployed environments, short token lifetimes, key rotation procedures, and Argon2 password hashes.
- Enforce role and resource ownership for each protected operation.
- Apply request-size limits; validate files if attachments are added.
- Add rate limits to login and costly AI requests before public deployment.
- Log request IDs and safe operational events; never log passwords, full tokens, provider keys, or unnecessary personal data.
- `/health` reports process health. Add DB readiness only after the database is configured.
- Review migrations and backup/rollback strategy before applying to production.

## 9. Decisions before implementation

Before database work, decide status transitions, priority scale, assignment history, note visibility, tenant/account boundaries, retention, and ownership policy. Before AI work, decide provider, model, retention terms, search/index technology, confidence thresholds, evaluation, human review, and which actions AI may suggest versus execute.

See [implementation-plan.md](implementation-plan.md) for suggested classes, methods, and build order.
