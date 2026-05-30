# Portfolio Backend - Implementation Roadmap
## 4-Week Sprint Plan to Production

**Goal**: Production-ready FastAPI backend with RAG chatbot and avatar integration, showcasing Clean Architecture + DDD + Hexagonal patterns.

**Timeline**: 4 weeks (MVP to v1.0)  
**Deployment Target**: Digital Ocean Droplet  
**Related Documents**: [PRD](./portfolio-backend-prd.md) | [Architecture](./portfolio-backend-architecture.md)

---

## Week 1: Foundation & Domain Layer

### Sprint Goal
Complete project structure, domain models, and local development environment.

### Tasks

#### Day 1-2: Project Setup
- [ ] **Initialize Repository**
  ```bash
  mkdir portfolio-backend && cd portfolio-backend
  git init
  poetry init  # Create pyproject.toml
  poetry add fastapi uvicorn supabase openai python-dotenv pydantic-settings
  poetry add --group dev pytest pytest-asyncio pytest-cov black ruff mypy
  ```

- [ ] **Create Folder Structure**
  ```
  src/
  ├── domain/
  │   ├── chatbot/
  │   │   ├── entities/
  │   │   ├── value_objects/
  │   │   ├── events/
  │   │   ├── repository.py
  │   │   └── services/
  │   ├── avatar/
  │   │   ├── entities/
  │   │   ├── value_objects/
  │   │   └── repository.py
  │   └── shared/
  │       ├── base_entity.py
  │       ├── base_value_object.py
  │       ├── domain_event.py
  │       └── errors.py
  ├── application/
  ├── infrastructure/
  └── __init__.py
  
  tests/
  ├── unit/
  │   ├── domain/
  │   └── application/
  ├── integration/
  ├── architecture/
  └── conftest.py
  
  docs/
  scripts/
  .github/workflows/
  ```

- [ ] **Configure Development Tools**
  ```toml
  # pyproject.toml
  [tool.black]
  line-length = 100
  
  [tool.ruff]
  line-length = 100
  
  [tool.mypy]
  python_version = "3.11"
  strict = true
  ```

#### Day 3-4: Domain Layer - Chatbot

- [ ] **Base Classes** (`src/domain/shared/`)
  - [ ] `base_entity.py`: Generic `Entity[ID]` and `AggregateRoot[ID]`
  - [ ] `base_value_object.py`: Generic `ValueObject` with equality
  - [ ] `domain_event.py`: Base `DomainEvent` class
  - [ ] `errors.py`: `DomainError`, `NotFoundError`, custom exceptions

- [ ] **Value Objects** (`src/domain/chatbot/value_objects.py`)
  - [ ] `ConversationId` with `generate()` and `from_string()`
  - [ ] `SessionId` with validation
  - [ ] `MessageId`, `MessageRole`, `MessageContent`
  - [ ] `SourceCitation` with relevance score validation
  - [ ] Write unit tests for each VO

- [ ] **Entities** (`src/domain/chatbot/entities/`)
  - [ ] `Message` entity with factory methods
  - [ ] `Conversation` aggregate root with invariants
  - [ ] Unit tests for `add_user_message()`, `add_assistant_response()`

- [ ] **Domain Events** (`src/domain/chatbot/events.py`)
  - [ ] `ConversationStarted`, `MessageSent`, `ResponseGenerated`

- [ ] **Repository Interface** (`src/domain/chatbot/repository.py`)
  - [ ] Define `IConversationRepository` abstract class

#### Day 5: Domain Layer - Avatar

- [ ] **Avatar Value Objects**
  - [ ] `AvatarSessionId`, `SessionToken`, `AvatarState` enum

- [ ] **Avatar Entity**
  - [ ] `AvatarSession` aggregate with expiration logic

- [ ] **Repository Interface**
  - [ ] `IAvatarSessionRepository`

#### Day 6-7: Unit Tests & Documentation

- [ ] **Domain Unit Tests**
  - Target: 90%+ coverage on domain layer
  - Test all invariants and validation rules

- [ ] **Architecture Tests**
  - [ ] Implement `test_domain_has_no_external_dependencies()`
  - [ ] Set up pre-commit hooks

- [ ] **Code Review Checkpoint**
  - Review domain model with team/mentor
  - Validate against DDD tactical patterns

**Week 1 Deliverable**: Pure domain layer with zero infrastructure dependencies, 90%+ test coverage.

---

## Week 2: Application Layer & Ports

### Sprint Goal
Implement use case handlers and define all port interfaces.

### Tasks

#### Day 8-9: Application Layer Structure

- [ ] **DTOs** (`src/application/chatbot/send_message/`)
  - [ ] `command.py`: `SendMessageCommand`
  - [ ] `response.py`: `SendMessageResponse`, `SourceDTO`

- [ ] **Driver Ports** (`src/application/chatbot/send_message/port.py`)
  - [ ] `ISendMessageUseCase` interface

- [ ] **Driven Ports** (`src/application/chatbot/ports/`)
  - [ ] `rag_service.py`: `IRAGService` interface with `RetrievedContext` DTO
  - [ ] `llm_service.py`: `ILLMService` interface with `LLMResponse` DTO

#### Day 10-11: Use Case Handlers

- [ ] **Send Message Handler**
  - [ ] Implement `SendMessageHandler` (from architecture doc)
  - [ ] Handle domain errors, map to application exceptions

- [ ] **Start Conversation Handler**
  - [ ] `StartConversationCommand`, `StartConversationHandler`
  - [ ] Create conversation, return conversation ID

- [ ] **Get Conversation Handler**
  - [ ] Query handler to retrieve conversation history

#### Day 12: Avatar Use Cases

- [ ] **Generate Token Handler**
  - [ ] `GenerateTokenCommand`, `GenerateTokenHandler`
  - [ ] Call `IAvatarAPIClient` driven port

- [ ] **Avatar Ports**
  - [ ] Define `IAvatarAPIClient` interface

#### Day 13-14: Unit Tests & Mocks

- [ ] **Test Doubles** (`src/infrastructure/adapters/driven/in_memory/`)
  - [ ] `InMemoryConversationRepository`
  - [ ] `FakeRAGService` (returns mock context)
  - [ ] `FakeLLMService` (returns canned responses)

- [ ] **Application Unit Tests**
  - [ ] Test each handler with fake/in-memory adapters
  - [ ] Verify domain event publishing
  - [ ] Test error paths (NotFoundError, DomainError)

- [ ] **Architecture Tests**
  - [ ] `test_application_has_no_infrastructure_dependencies()`

**Week 2 Deliverable**: Complete application layer with all use cases, 85%+ test coverage, all tests passing.

---

## Week 3: Infrastructure Layer & Integration

### Sprint Goal
Implement all adapters (REST, Supabase, OpenAI), integrate external systems.

### Tasks

#### Day 15: Environment Setup

- [ ] **Supabase Setup**
  - [ ] Create Supabase project
  - [ ] Run migrations for `conversations`, `messages`, `embeddings` tables
  - [ ] Enable pgvector extension
  - [ ] Test connection from local environment

- [ ] **OpenAI API**
  - [ ] Get API key, set up billing alerts
  - [ ] Test embeddings endpoint locally
  - [ ] Test chat completions endpoint

- [ ] **Settings Configuration** (`src/infrastructure/config/settings.py`)
  ```python
  from pydantic_settings import BaseSettings
  
  class Settings(BaseSettings):
      OPENAI_API_KEY: str
      SUPABASE_URL: str
      SUPABASE_KEY: str
      DATABASE_URL: str
      LIVEAVATAR_API_KEY: str
      SENTRY_DSN: str | None = None
      ENVIRONMENT: str = "development"
      
      class Config:
          env_file = ".env"
  ```

#### Day 16-17: Driven Adapters (Outbound)

- [ ] **Supabase Repository**
  - [ ] `SupabaseConversationRepository` implementation
  - [ ] `ConversationMapper` for domain ↔ persistence
  - [ ] Integration tests with test database

- [ ] **OpenAI Services**
  - [ ] `OpenAIEmbeddingsService` (implements `IEmbeddingsService`)
  - [ ] `OpenAILLMService` (implements `ILLMService`)
  - [ ] `OpenAIRAGService` (combines embeddings + vector search)
  - [ ] Mock tests + live integration tests (with real API, gated by env var)

- [ ] **LiveAvatar Client**
  - [ ] `LiveAvatarClient` (implements `IAvatarAPIClient`)
  - [ ] Token generation, error handling

#### Day 18-19: Driver Adapters (Inbound)

- [ ] **FastAPI Setup** (`src/infrastructure/main.py`)
  ```python
  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware
  
  app = FastAPI(title="Portfolio Backend", version="1.0.0")
  
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://your-portfolio.com"],
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

- [ ] **REST Controllers** (`src/infrastructure/adapters/driver/rest/`)
  - [ ] `chatbot_controller.py`: POST /conversations, POST /messages, GET /conversations/{id}
  - [ ] `avatar_controller.py`: POST /avatar/token
  - [ ] Health check endpoint: GET /health

- [ ] **Dependency Injection** (`src/infrastructure/config/dependencies.py`)
  - [ ] `get_send_message_use_case()` composition root
  - [ ] Wire up all dependencies

#### Day 20: WebSocket (Avatar State)

- [ ] **WebSocket Handler** (`src/infrastructure/adapters/driver/websocket/`)
  - [ ] Endpoint: `/ws/avatar/{session_id}`
  - [ ] Broadcast avatar state changes (idle, listening, speaking, thinking)

#### Day 21: Testing & Integration

- [ ] **Integration Tests**
  - [ ] E2E test: Create conversation → Send message → Verify response
  - [ ] Test with real Supabase (test project)
  - [ ] Test OpenAI integration (with budget limits)

- [ ] **Seed Data Script** (`scripts/seed_embeddings.py`)
  - [ ] Parse CV PDF → chunks
  - [ ] Generate embeddings via OpenAI
  - [ ] Store in Supabase `embeddings` table
  - [ ] Verify semantic search works

**Week 3 Deliverable**: Fully integrated backend, running locally, all tests green, embeddings seeded.

---

## Week 4: Deployment, Monitoring, & Polish

### Sprint Goal
Deploy to production, set up monitoring, write documentation.

### Tasks

#### Day 22: Deployment Setup

- [ ] **Docker** (`Dockerfile`)
  ```dockerfile
  FROM python:3.11-slim
  
  WORKDIR /app
  
  COPY pyproject.toml poetry.lock ./
  RUN pip install poetry && poetry install --no-dev
  
  COPY . .
  
  CMD ["poetry", "run", "uvicorn", "src.infrastructure.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

- [ ] **Docker Compose** (`docker-compose.yml`)
  - Backend service
  - Nginx reverse proxy
  - SSL setup (Let's Encrypt)

- [ ] **Digital Ocean**
  - [ ] Create Droplet (2GB RAM, Ubuntu 22.04)
  - [ ] Install Docker, Docker Compose
  - [ ] Set up SSH keys
  - [ ] Configure firewall (ports 80, 443, 22)

#### Day 23: CI/CD

- [ ] **GitHub Actions** (`.github/workflows/ci.yml`)
  - [ ] Run tests on every PR
  - [ ] Check code coverage (fail if <85%)
  - [ ] Run architecture tests

- [ ] **Deployment Workflow** (`.github/workflows/deploy.yml`)
  - [ ] Build Docker image on main branch push
  - [ ] SSH to Droplet, pull image, restart services
  - [ ] Zero-downtime deployment (health checks)

#### Day 24: Monitoring & Observability

- [ ] **Sentry Setup**
  - [ ] Initialize Sentry SDK in `main.py`
  - [ ] Test error reporting

- [ ] **Logging**
  - [ ] Structured logging (JSON format)
  - [ ] Log levels: INFO for requests, ERROR for failures

- [ ] **Metrics** (Optional)
  - [ ] Prometheus metrics endpoint
  - [ ] Track: request count, latency, token usage

#### Day 25: API Documentation

- [ ] **OpenAPI/Swagger**
  - [ ] Enhance FastAPI docstrings
  - [ ] Add examples to Pydantic models
  - [ ] Test Swagger UI at `/docs`

- [ ] **README.md**
  ```markdown
  # Portfolio Backend
  
  ## Architecture
  - Clean Architecture + DDD + Hexagonal
  - FastAPI, Supabase, OpenAI
  
  ## Local Development
  poetry install
  cp .env.example .env
  poetry run uvicorn src.infrastructure.main:app --reload
  
  ## Testing
  poetry run pytest
  
  ## Deployment
  Deployed on Digital Ocean via GitHub Actions
  ```

#### Day 26: RAG Benchmarking

- [ ] **Evaluation Suite** (`tests/rag/benchmark_eval.py`)
  - [ ] Run 20 benchmark questions
  - [ ] Calculate accuracy, citation rate
  - [ ] Generate report

- [ ] **Prompt Optimization**
  - [ ] Tune system prompt based on eval results
  - [ ] Adjust chunk size if accuracy <90%

#### Day 27: Security Audit

- [ ] **Security Checklist**
  - [ ] Input validation on all endpoints
  - [ ] Rate limiting (10 req/min per IP for avatar, 30 for chatbot)
  - [ ] CORS configured correctly
  - [ ] Secrets not in code/logs
  - [ ] SQL injection prevention (parameterized queries)

- [ ] **Dependency Audit**
  - [ ] Run `poetry audit` (check for CVEs)
  - [ ] Update vulnerable packages

#### Day 28: Final Polish & Launch

- [ ] **Performance Testing**
  - [ ] Load test: 100 concurrent users
  - [ ] Verify P95 latency <500ms

- [ ] **Final Deployment**
  - [ ] Deploy v1.0 to production
  - [ ] Run smoke tests on production API
  - [ ] Monitor Sentry for errors

- [ ] **Documentation**
  - [ ] Update README with live API URL
  - [ ] Add architecture diagrams to docs/
  - [ ] Write blog post about the architecture (optional)

**Week 4 Deliverable**: Production deployment live at `https://api.richardayala.dev`, monitoring active, 90%+ RAG accuracy.

---

## Post-Launch: v1.1 Improvements (Optional, Week 5-6)

### Optimization Backlog

- [ ] **Response Streaming**
  - [ ] Server-Sent Events (SSE) for typing effect
  - [ ] Stream LLM responses token-by-token

- [ ] **Caching Layer**
  - [ ] Redis cache for embeddings lookup
  - [ ] Cache frequent queries (LRU cache)

- [ ] **Enhanced Metrics**
  - [ ] Grafana dashboard
  - [ ] Cost tracking (OpenAI token usage by endpoint)

- [ ] **Multi-turn Memory**
  - [ ] RAG over conversation history
  - [ ] "You mentioned earlier..." context awareness

- [ ] **Admin Endpoints**
  - [ ] POST /admin/embeddings/refresh (re-seed knowledge base)
  - [ ] GET /admin/metrics (token usage, costs)

---

## Risk Mitigation Matrix

| Risk | When | Mitigation Plan |
|------|------|----------------|
| **OpenAI API Down** | Week 3, Day 17 | Implement circuit breaker, retry with exponential backoff, fallback to cached responses |
| **RAG Accuracy <90%** | Week 4, Day 26 | Adjust chunk size (512→256 tokens), expand knowledge base, tune prompt, lower threshold to 0.70 |
| **Deployment Issues** | Week 4, Day 28 | Test deployment to staging droplet first, keep rollback script ready, health check before traffic switch |
| **Cost Overrun** | Any time | Set OpenAI budget alerts at $10, $25, $50; use cheaper model (3.5-turbo) for dev/testing |
| **Dependency Rule Violations** | Week 2-3 | Run architecture tests in pre-commit hook, fail CI if violations detected |

---

## Success Metrics (End of Week 4)

| Metric | Target | Measurement |
|--------|--------|-------------|
| **RAG Accuracy** | ≥90% | 20-question benchmark suite |
| **API Latency (P95)** | <500ms | Load testing with 100 users |
| **Test Coverage** | ≥85% | pytest-cov report |
| **Architecture Compliance** | 100% | Architecture tests pass |
| **Deployment Uptime** | 99.5% | Uptime monitoring (1 week) |
| **OpenAI Cost** | <$5 | First week production usage |

---

## Daily Standup Template

**What I completed yesterday:**
- [ ] Task 1
- [ ] Task 2

**What I'm working on today:**
- [ ] Task 3

**Blockers:**
- None / [Describe blocker]

**Key decision needed:**
- [Decision, if any]

---

## Quick Reference Commands

### Development
```bash
# Start server
poetry run uvicorn src.infrastructure.main:app --reload

# Run tests
poetry run pytest -v

# Run tests with coverage
poetry run pytest --cov=src --cov-report=html

# Run only architecture tests
poetry run pytest tests/architecture/ -v

# Format code
poetry run black src/ tests/
poetry run ruff check src/ tests/ --fix

# Type check
poetry run mypy src/
```

### Database
```bash
# Seed embeddings
poetry run python scripts/seed_embeddings.py

# Run migrations (future)
poetry run alembic upgrade head
```

### Deployment
```bash
# Build Docker image
docker build -t portfolio-backend .

# Run locally with Docker
docker-compose up

# Deploy to production (via GitHub Actions)
git push origin main  # Triggers deployment workflow
```

---

## Resources

### Documentation
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) - Uncle Bob
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) - Alistair Cockburn
- [DDD Blue Book](https://www.domainlanguage.com/ddd/blue-book/) - Eric Evans
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Supabase Python Docs](https://supabase.com/docs/reference/python/introduction)
- [OpenAI API Docs](https://platform.openai.com/docs/api-reference)

### Example Repositories
- [bxcodec/go-clean-arch](https://github.com/bxcodec/go-clean-arch) - Go reference
- [cdddg/py-clean-arch](https://github.com/cdddg/py-clean-arch) - Python reference

### Tools
- [Architecture Decision Records](https://adr.github.io/) - Document key decisions
- [Conventional Commits](https://www.conventionalcommits.org/) - Commit message format
- [GitFlow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow) - Branching strategy

---

**END OF ROADMAP**

**Next Action**: Initialize repository and start Week 1, Day 1 tasks.
