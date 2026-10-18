# Step-by-Step Implementation Plan

This plan turns [architecture.md](architecture.md) into an ordered development path. It describes proposed files, classes, and method responsibilities; these classes and methods are not implemented yet. Work one phase at a time and review behavior before moving on.

## Working rules

- Routers validate, authorize, call a use case, and return a response. Keep them thin.
- Services own business rules and transaction boundaries.
- Repositories accept a SQLAlchemy `Session` and do not commit.
- Pydantic schemas define API input/output. SQLAlchemy models define persistence. Do not use one class for both.
- Always scope queries by authorization context. UI filtering is not security.
- Add tests as features are implemented. Do not create or run migrations until the schema is reviewed and approved.

## Phase 0 — Agree on domain rules

Before database implementation, decide:

1. Roles and actions allowed for customer, agent, and administrator; whether a user may have multiple roles.
2. Ticket statuses and allowed transitions; priority values and who may set them.
3. Whether assignment changes require full history.
4. Whether customers can see only their own records and which staff can see all tickets.
5. How internal notes differ from customer-visible replies.
6. Tenant/account boundaries, deletion, retention, and audit requirements.

**Deliverable:** approved domain rules and initial data model. Do not generate a migration before this review.

## Phase 1 — Backend foundations

### Settings and app construction

Create `backend/app/core/config.py`:

- `class Settings(BaseSettings)`: reads app environment, database URL, token configuration, and CORS origins from environment variables.
- `get_settings() -> Settings`: returns a cached settings object. Fail startup for missing production configuration; use safe defaults only in development.

Update `backend/app/main.py`:

- `create_app() -> FastAPI`: constructs the app, attaches metadata, middleware, exception handlers, and the root router.
- Keep `/health` as process health. Add a lifespan handler only when managed resources such as engines/HTTP clients need startup and shutdown behavior.

Create `backend/app/api/router.py`:

- `api_router = APIRouter(prefix="/api/v1")`: combines feature routers. Include it from `create_app()`.

### Database engine/session

Create `backend/app/db/base.py`:

- `class Base(DeclarativeBase)`: shared SQLAlchemy metadata base for ORM models.

Create `backend/app/db/session.py`:

- `create_engine(settings) -> Engine`: builds the SQLAlchemy engine from `DATABASE_URL` using `postgresql+psycopg://...`.
- `SessionLocal`: session factory, configured consistently (for example, `autoflush=False`, `expire_on_commit=False`).
- `get_db_session() -> Generator[Session, None, None]`: yields one request-scoped session and always closes it in `finally`.
- Add a readiness query only when database configuration is intentionally introduced; do not connect at module import.

**Connection chain:** settings provide a URL; SQLAlchemy parses it and builds SQL; the PostgreSQL dialect calls Psycopg; Psycopg connects to a running PostgreSQL server; PostgreSQL executes statements and returns rows. Psycopg is a Python connector/driver, not the server. `psycopg[binary]` supplies driver binaries but does not install PostgreSQL.

Create `backend/app/core/exceptions.py` with domain exceptions such as `NotFoundError`, `ForbiddenError`, `ConflictError`, and `InvalidTransitionError`. Add Pydantic `ErrorDetail` and `ErrorResponse` schemas, then register centralized FastAPI handlers that return consistent, safe JSON errors. A response should look like `{"error":{"code":"not_found","message":"Ticket not found.","details":[],"request_id":"req_..."}}`. Never return stack traces, SQL, credentials, tokens, or internal notes. Keep module-specific policy close to its feature rather than making one generic helper file for everything.

## Phase 2 — Identity, authentication, and authorization

Suggested files: `modules/users/{models,schemas,repository,service}.py`, `modules/auth/{router,service}.py`, and shared `core/security.py`.

### Classes

- `User` (ORM model): ID, normalized email, password hash, role, active flag, timestamps. It is persistence data, not an API schema.
- `UserCreate`, `UserRead`, `LoginRequest`, `TokenResponse` (Pydantic): validate input and allowlist fields in responses. `TokenResponse` contains `access_token`, `token_type` (normally `bearer`), and `expires_in` seconds.
- `UserRepository(session)`: `get_by_id(user_id)`, `get_by_email(email)`, and `add(user)`; performs persistence queries only and never commits.
- `PasswordService`: `hash_password(plain: str) -> str` uses pwdlib/Argon2; `verify_password(plain: str, hashed: str) -> bool` checks a submitted value without revealing which credential was wrong.
- `TokenService`: `create_access_token(subject: str, role: str, expires_in: timedelta) -> str` signs a short-lived JWT; `decode_access_token(token: str) -> TokenClaims` verifies signature, expected algorithm, and expiry. Never trust an algorithm supplied by the token.
- `AuthService`: `register_user(data) -> User` normalizes email, checks duplicates, hashes password, and stores the user; `authenticate(email, password) -> User` verifies credentials and active status; `issue_access_token(user) -> TokenResponse` creates the token response.
- `get_current_user(...) -> User` (FastAPI dependency): reads bearer token, validates it, loads the identity, and rejects missing/inactive users.
- `require_roles(*roles)` (dependency factory): checks broad role access. It does not replace per-record ownership checks.

### Endpoints

- `POST /api/v1/auth/register` only if public registration is approved; otherwise create accounts through restricted staff workflows.
- `POST /api/v1/auth/login`: accepts email/password and returns an access token.
- `GET /api/v1/auth/me`: returns the current user's safe profile.

Return generic invalid-credential errors. Never store or log raw passwords or full tokens. Decide refresh-token/revocation behavior before claiming those features. Add rate limiting before public deployment.

## Phase 3 — Customer and agent profiles

Suggested modules: `modules/customers/` and `modules/agents/`.

- `CustomerProfile` (ORM): customer-specific data linked to a user; define uniqueness and deletion rules in the schema review.
- `AgentProfile` (ORM): staff-specific fields such as display name, team, or availability if needed.
- Pydantic schemas: `CustomerCreate`, `CustomerUpdate`, `CustomerRead`, `AgentCreate`, `AgentRead`; explicitly separate writable and read-only fields.
- `CustomerRepository`: `get_by_id`, `get_by_user_id`, `add`, and approved update operations.
- `AgentRepository`: `get_by_id`, `list_active`, and approved update operations.
- `CustomerService`: create/update profiles and enforce self-versus-staff permissions.
- `AgentService`: manage staff profile data and check assignment eligibility.

Do not place password fields on profile schemas; credentials belong to the users/auth boundary.

## Phase 4 — Ticket domain and API

Suggested module files: `modules/tickets/{models,schemas,repository,service,router}.py`.

### Models and schemas

- `Ticket` (ORM): customer ID, subject, description, status, priority, optional assigned-agent ID, timestamps.
- `TicketStatus`, `TicketPriority` (Python enums): canonical values; confirm these before coding transitions.
- `TicketCreate`: customer-writable fields only. Reject protected values such as assignment or privileged status from customers.
- `TicketUpdate`: narrowly scoped optional changes, or separate request schemas for status and assignment actions.
- `TicketRead`: safe response with `id`, `subject`, `description` (if the caller may view it), `status`, `priority`, `customer_id`, `assigned_agent_id`, `created_at`, and `updated_at`. Never include ORM internals or secret fields.
- `TicketListResponse`: `{items: list[TicketRead], page: int, page_size: int, total: int, has_next: bool}`. Apply role and ownership filtering before calculating/returning the collection.

For a single successful ticket endpoint, return the `TicketRead` object directly; for a list, return `TicketListResponse`. Do not put success responses inside a second generic `data` wrapper. Use the shared `ErrorResponse` envelope for errors. The complete JSON examples and status code guidance are in [architecture.md](architecture.md#response-structure).

### Repository methods

`TicketRepository(session)` could provide:

- `get_by_id(ticket_id) -> Ticket | None`
- `list_for_customer(customer_id, filters, page) -> Page[Ticket]`
- `list_for_agent(agent_id, filters, page) -> Page[Ticket]`
- `list_for_staff(filters, page) -> Page[Ticket]`
- `add(ticket) -> Ticket`
- `flush()`: make generated IDs available before adding related history rows

The repository implements query/persistence details. The service must choose an access-scoped query; do not rely on the frontend to hide records.

### Service methods

`TicketService(session, ticket_repo, history_repo, customer_service, agent_service)` could expose:

- `create_ticket(actor, data) -> Ticket`: derive customer identity from the authenticated actor (or verify permitted staff action), set safe defaults, and create the ticket plus initial history in one transaction.
- `get_ticket(actor, ticket_id) -> Ticket`: fetch and enforce ownership/staff access.
- `list_tickets(actor, filters, page) -> Page[Ticket]`: route to an appropriately scoped list query based on actor role.
- `assign_ticket(actor, ticket_id, agent_id) -> Ticket`: require staff permission, verify the agent is eligible, update assignment, and record history.
- `change_status(actor, ticket_id, new_status) -> Ticket`: check permission and allowed transition, update the timestamp, and record history atomically.
- `change_priority(actor, ticket_id, new_priority) -> Ticket`: enforce the agreed role policy and record the change.

The service owns `with session.begin():` transaction boundaries. Repositories may flush but must not independently commit.

### Router methods

`ticket_router` handlers translate HTTP to service calls; they should not contain SQL or business policy:

- `create_ticket(payload, current_user, db)`: `POST /tickets`, returns `201` and `TicketRead`.
- `list_tickets(filters, page, current_user, db)`: `GET /tickets`, returns only authorized results.
- `get_ticket(ticket_id, current_user, db)`: `GET /tickets/{ticket_id}`.
- `assign_ticket(ticket_id, payload, current_user, db)`: `PATCH /tickets/{ticket_id}/assignment`.
- `change_ticket_status(ticket_id, payload, current_user, db)`: `PATCH /tickets/{ticket_id}/status`.

## Phase 5 — Conversation and audit history

Suggested module: `modules/conversations/`; ticket event records may live in a history module if they grow independently.

- `ConversationMessage` (ORM): ticket ID, author user ID, body, visibility (`public`/`internal`), timestamp; enforce a size limit.
- `TicketEvent` (ORM): ticket ID, actor ID, event type, safe before/after summary, timestamp. Do not store secrets in event payloads.
- `CommentCreate`, `ConversationItemRead` (Pydantic): validate inputs and shape timeline output.
- `ConversationRepository`: `add_message`, `list_messages(ticket_id, visibility_filter)`, `add_event`, `list_events`.
- `ConversationService.add_comment(actor, ticket_id, body, visibility)`: authorize the ticket; permit internal notes only for staff; store message and activity atomically.
- `ConversationService.get_timeline(actor, ticket_id, page)`: authorize and omit internal notes from customer-visible results.
- Router: `POST /tickets/{ticket_id}/comments`, `GET /tickets/{ticket_id}/conversation`.

Tests must prove customers cannot read or create internal notes.

## Phase 6 — Schema review and migrations

Only after data rules are approved:

1. Ensure all ORM models are imported so `Base.metadata` includes them.
2. Review relationships, foreign keys, uniqueness, indexes, deletion rules, and enum storage.
3. Configure Alembic to use application settings and `Base.metadata`.
4. Generate a revision and inspect the generated migration; never assume it is correct automatically.
5. Apply to a disposable local/test PostgreSQL database first.
6. Verify upgrade and downgrade expectations; back up production data before migration.

Do not use `Base.metadata.create_all()` as a replacement for reviewed migrations in regular environments.

## Phase 7 — Frontend API and screens

Suggested structure as needed:

```text
frontend/src/
├── api/{client,auth,tickets}.js
├── auth/
├── components/
├── pages/
├── routes/
├── App.jsx
└── main.jsx
```

- `api/client.js`: central API base URL, JSON headers, token attachment, response parsing, and consistent error handling. No server secrets here.
- `AuthProvider`: frontend identity state for presentation; the backend remains authoritative.
- `LoginPage`: submits credentials and presents validation/errors without logging credentials.
- `TicketListPage`: calls the scoped list endpoint; handles filters, pagination, loading, empty, and error states.
- `TicketDetailPage`: loads a permitted ticket/timeline, posts a reply, and shows status/assignment controls based on role.
- Reusable components: `TicketStatusBadge`, `PriorityBadge`, `TicketForm`, `ConversationTimeline`, accessible form controls.

Build the API client/login before ticket pages. Replace template content only as the product screens are implemented; avoid hardcoded fake tickets after API integration.

## Phase 8 — Knowledge and AI assistance (Part 2)

Keep AI logic out of ticket repositories and HTTP handlers. Add only after provider, data retention, and safety policy are chosen.

- `KnowledgeArticle` and `KnowledgeChunk` (ORM): approved content and traceable source/version data, after the index choice is made.
- `DocumentIngestionService`: validate documents, extract text, split into traceable chunks, and update the index.
- `KnowledgeRepository.search(query, filters, limit)`: return relevant chunks with source metadata; implementation depends on selected search technology.
- `AIProvider` interface: `generate_response(messages, context, options) -> AIResponse`; `summarize_conversation(messages) -> Summary`. Provider adapter implements it.
- `AIService.suggest_reply(ticket_id, actor)`: load authorized context, retrieve approved knowledge, call provider through HTTPX, validate and audit the draft, return sources.
- `AIService.suggest_category(text)` and `suggest_priority(text)`: return recommendations, confidence, and reasons; do not silently change a ticket.
- `EscalationPolicy.should_escalate(result, context)`: escalate low confidence, safety-sensitive, unsupported, or failed cases.
- `AIReview`/audit record: retain approved suggestion metadata and reviewer decision according to retention policy.

Guardrails: send only necessary data; use timeouts and bounded retries; treat retrieved documents as untrusted input; exclude internal notes; require human approval for customer-facing replies initially; provide human-support fallback.

## Phase 9 — Tests and release readiness

Add tests alongside each service. Use a disposable PostgreSQL database for integration checks of PostgreSQL-specific behavior. Use dependency overrides or mocks for isolated unit/API tests, but do not mock away the authorization rule under test.

- Unit: token/password handling, status transitions, ticket access, pagination, escalation policy.
- API: login, customer ticket creation, ownership, agent assignment/status, internal-note privacy, validation/errors.
- Integration: repositories and migrations against disposable PostgreSQL.
- Frontend: loading/error states, role-aware controls, forms, and conversation timeline.
- Future AI: retrieval quality/source attribution, refusal/escalation, prompt injection resistance, timeouts, provider failure fallback.

Before release: validate configuration, exclude secrets, review migrations, use a least-privilege DB account, enable HTTPS, narrow CORS, apply rate limits, keep logs safe, and prepare backups/monitoring/rollback.

## Build order summary

1. Agree on roles, ticket rules, privacy, and data ownership.
2. Add settings, app/router structure, errors, SQLAlchemy engine, and session dependency.
3. Add identity, password hashing, JWTs, and role/ownership dependencies.
4. Add customer and agent profiles.
5. Add ticket model/schema/repository/service/router and behavior tests.
6. Add conversation messages, internal-note privacy, and ticket history.
7. Approve schema and add/review Alembic migrations against disposable PostgreSQL.
8. Build frontend API client, login, ticket list/detail, and conversation screens.
9. Add knowledge ingestion/retrieval and the AI provider interface in Part 2.
10. Add AI suggestions, summaries, classification, human approval/escalation, and evaluation.
11. Prepare deployment, security, observability, backup, and operational runbooks.
