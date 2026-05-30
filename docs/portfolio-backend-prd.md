# Product Requirements Document (PRD)
## Portfolio Backend System - AI-Powered Professional Showcase

**Version:** 1.0  
**Author:** Richard Xavier Ayala Funes  
**Date:** March 16, 2026  
**Status:** Draft for Review  

---

## 1. Executive Summary

### Problem Statement
Traditional static portfolios fail to demonstrate real-world backend engineering capabilities. Recruiters and technical evaluators need to see actual implementations of Clean Architecture, DDD, and Hexagonal patterns in action, not just descriptions. Additionally, visitors struggle to extract relevant information from lengthy CVs and project descriptions, leading to missed opportunities.

### Proposed Solution
A production-grade FastAPI backend implementing Clean Architecture + DDD + Hexagonal patterns, featuring two core systems:
1. **AI Chatbot with RAG** - Intelligent conversational interface with semantic search over CV and project data
2. **Real-time Avatar Integration** - LiveAvatar.com token generation for animated professional presence

This backend serves as both a functional portfolio feature AND a technical showcase demonstrating enterprise-grade architecture patterns.

### Success Criteria
1. **API Response Time**: P95 latency < 500ms for chatbot queries, < 200ms for avatar token generation
2. **RAG Accuracy**: >= 90% answer relevance score on benchmark questions about CV/projects
3. **Architecture Compliance**: 100% adherence to Clean Architecture dependency rules (verified via architecture tests)
4. **Test Coverage**: >= 85% unit test coverage, >= 70% integration test coverage
5. **Deployment Success**: Zero-downtime deployment on Digital Ocean with automated CI/CD

---

## 2. User Experience & Functionality

### User Personas

**Primary Persona: Technical Recruiter**
- Goal: Quickly assess backend engineering capabilities
- Pain: Needs to verify Clean Architecture/DDD knowledge beyond resume claims
- Behavior: Explores live chatbot, reviews API documentation, examines GitHub repository

**Secondary Persona: Hiring Manager / Tech Lead**
- Goal: Evaluate system design and code quality
- Pain: Wants to see real-world implementation, not toy projects
- Behavior: Deep-dives into architecture decisions, reviews test coverage, checks deployment setup

**Tertiary Persona: Casual Visitor**
- Goal: Learn about Richard's background and projects
- Pain: Too much information to read through
- Behavior: Uses chatbot to ask specific questions

### User Stories

#### Epic 1: AI Chatbot with RAG

**US-001: Basic Conversation**
- **Story**: As a visitor, I want to ask questions about Richard's background in natural language, so that I can quickly find relevant information without reading the entire CV.
- **Acceptance Criteria**:
  - User can send text messages via `/chat` route UI
  - System responds within 3 seconds for 95% of queries
  - Responses cite specific sources (CV sections, project names)
  - Conversation history persists for the session
  - System handles unclear questions with clarifying follow-ups

**US-002: Technical Deep-Dive**
- **Story**: As a technical recruiter, I want to ask detailed questions about specific technologies and projects, so that I can verify expertise claims.
- **Acceptance Criteria**:
  - Chatbot can answer questions like "What AI models has Richard worked with?"
  - Responses include specific project examples with context
  - System differentiates between professional and educational experience
  - Answers include timeframes and team sizes when relevant

**US-003: Semantic Search**
- **Story**: As a hiring manager, I want the chatbot to understand intent (not just keywords), so that I get accurate answers even with vague queries.
- **Acceptance Criteria**:
  - Query "Has he built APIs?" returns FastAPI and Django experience
  - Query "Can he work with databases?" returns PostgreSQL, MongoDB mentions
  - Synonym handling: "LLMs" = "Large Language Models" = "AI models"
  - Semantic similarity threshold: >= 0.75 for relevant chunk retrieval

#### Epic 2: Real-time Avatar Integration

**US-004: Avatar Token Generation**
- **Story**: As the portfolio owner, I want to generate LiveAvatar.com session tokens on-demand, so that visitors see an animated professional presence without exposing API keys.
- **Acceptance Criteria**:
  - Frontend calls `/api/avatar/token` endpoint
  - Backend generates valid LiveAvatar.com session token
  - Token expiration: 30 minutes
  - Rate limit: 10 requests per IP per hour
  - No API keys exposed to frontend

**US-005: Avatar State Management**
- **Story**: As a visitor, I want the avatar to reflect conversation state (idle, listening, speaking), so that the interaction feels natural.
- **Acceptance Criteria**:
  - Backend provides WebSocket endpoint for avatar state sync
  - States: idle, listening, speaking, thinking
  - State transitions triggered by chatbot events
  - Fallback to polling if WebSocket unavailable

### Non-Goals (Out of Scope for v1.0)

❌ **User Authentication** - No login system; chatbot is public
❌ **Admin Panel** - Content managed via Git/environment variables
❌ **Analytics Dashboard** - Basic logging only; no analytics UI
❌ **Multi-language Support** - English only
❌ **Voice Input** - Text-based chatbot only
❌ **Persistent User Profiles** - No long-term conversation memory across sessions
❌ **Custom Avatar Creation** - LiveAvatar.com provides avatar; no custom uploads
❌ **Payment Integration** - No premium features or paywalls

---

## 3. AI System Requirements

### RAG System Architecture

#### Knowledge Base Sources
1. **CV Content** (`CV_Richard_Ayala_Funes.pdf`)
   - Professional experience (companies, roles, dates, responsibilities)
   - Education and certifications
   - Technical skills matrix
   
2. **Project Data** (from `portfolio-web/docs/business_case.md` and future project files)
   - Project descriptions
   - Technologies used
   - Business impact metrics

3. **Static Content** (from frontend `src/data/` files)
   - Skills taxonomy
   - Detailed project case studies

#### Embedding Strategy
- **Model**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Chunking Strategy**:
  - CV: Section-based chunks (each role = 1 chunk, ~300-500 tokens)
  - Projects: Project-based chunks (each project = 1-2 chunks)
  - Max chunk size: 512 tokens with 50-token overlap
- **Vector Store**: Supabase (PostgreSQL with pgvector extension)
- **Similarity Search**: Cosine similarity, top-k=5 chunks, threshold >= 0.75

#### LLM Configuration
- **Primary Model**: OpenAI GPT-4o-mini (cost-optimized, sufficient for Q&A)
- **Fallback Model**: GPT-3.5-turbo (if 4o-mini unavailable)
- **System Prompt Template**:
  ```
  You are an AI assistant representing Richard Xavier Ayala Funes, a Backend and AI Engineer.
  Answer questions about his professional background, projects, and technical expertise.
  
  Context from knowledge base:
  {retrieved_chunks}
  
  Rules:
  - Always cite sources (e.g., "In his role at Purrfect Hire...")
  - If uncertain, say "I don't have information about that"
  - Keep responses concise (2-3 paragraphs max)
  - Use technical terminology appropriate for the audience
  ```
- **Temperature**: 0.3 (factual, low creativity)
- **Max Tokens**: 500 (concise responses)

#### Evaluation Strategy

**Benchmark Dataset** (20 questions minimum):
```
1. "What companies has Richard worked for?"
   Expected: Purrfect Hire, Indra, Sonrisas y Salud (with dates)

2. "Has he built AI systems?"
   Expected: RAG chatbot, LLM workflows, OpenAI API integration examples

3. "What's his experience with Clean Architecture?"
   Expected: Purrfect Hire ATS backend, FastAPI + Clean Architecture

4. "Can he work with Docker?"
   Expected: Yes, Docker/Podman experience at Indra, CI/CD pipelines

5. "What databases has he used?"
   Expected: PostgreSQL, MongoDB, Supabase
```

**Success Metrics**:
- **Answer Relevance**: >= 90% (manual eval: does answer address question?)
- **Factual Accuracy**: 100% (no hallucinated jobs/skills)
- **Citation Rate**: >= 80% (responses include source references)
- **Response Time**: P95 < 3 seconds (end-to-end)

**Testing Protocol**:
1. Automated eval suite runs on every RAG system change
2. Manual review of 10 random conversations weekly
3. Red-team testing: try to make system hallucinate (adversarial prompts)

### LiveAvatar.com Integration

#### API Requirements
- **Endpoint**: `https://api.liveavatar.com/v1/token` (hypothetical; adjust to actual API)
- **Authentication**: API key in environment variable `LIVEAVATAR_API_KEY`
- **Request Format**:
  ```json
  {
    "avatar_id": "professional_richard_v1",
    "session_duration_minutes": 30,
    "features": ["lip_sync", "idle_animation"]
  }
  ```
- **Response Format**:
  ```json
  {
    "token": "eyJhbGc...",
    "expires_at": "2026-03-16T15:30:00Z",
    "websocket_url": "wss://avatar.liveavatar.com/session/..."
  }
  ```

#### Error Handling
- **API Unavailable**: Return cached default avatar config (static image fallback)
- **Rate Limit Exceeded**: Return 429 with retry-after header
- **Invalid API Key**: Log error, return 500, send alert to monitoring

---

## 4. Technical Specifications

### Architecture Overview

#### Layers (Clean Architecture + DDD + Hexagonal)

```
src/
├── domain/                           # LAYER 1: Pure Business Logic
│   ├── chatbot/
│   │   ├── entities/
│   │   │   ├── conversation.py       # Aggregate root
│   │   │   ├── message.py            # Entity
│   │   │   └── query_result.py       # Entity
│   │   ├── value_objects/
│   │   │   ├── conversation_id.py
│   │   │   ├── message_content.py
│   │   │   ├── relevance_score.py
│   │   │   └── source_citation.py
│   │   ├── events/
│   │   │   ├── conversation_started.py
│   │   │   ├── message_sent.py
│   │   │   └── query_answered.py
│   │   ├── repository.py             # Interface (driven port)
│   │   └── services/
│   │       └── response_validator.py # Domain service
│   ├── avatar/
│   │   ├── entities/
│   │   │   └── avatar_session.py     # Aggregate root
│   │   ├── value_objects/
│   │   │   ├── session_token.py
│   │   │   └── avatar_state.py
│   │   └── repository.py             # Interface
│   └── shared/
│       ├── base_entity.py
│       ├── base_value_object.py
│       └── errors.py                 # Domain exceptions
│
├── application/                      # LAYER 2: Use Cases
│   ├── chatbot/
│   │   ├── start_conversation/
│   │   │   ├── command.py            # DTO
│   │   │   ├── handler.py            # Use case implementation
│   │   │   └── port.py               # Driver port (interface)
│   │   ├── send_message/
│   │   │   ├── command.py
│   │   │   ├── handler.py
│   │   │   └── port.py
│   │   └── ports/
│   │       ├── rag_service.py        # Driven port for RAG
│   │       └── llm_service.py        # Driven port for LLM
│   ├── avatar/
│   │   ├── generate_token/
│   │   │   ├── command.py
│   │   │   ├── handler.py
│   │   │   └── port.py
│   │   └── ports/
│   │       └── avatar_api_client.py  # Driven port
│   └── shared/
│       └── unit_of_work.py           # Transaction boundary
│
└── infrastructure/                   # LAYER 3: Adapters
    ├── adapters/
    │   ├── driver/                   # Inbound
    │   │   ├── rest/
    │   │   │   ├── chatbot_controller.py
    │   │   │   ├── avatar_controller.py
    │   │   │   └── websocket_handler.py
    │   │   └── cli/
    │   │       └── seed_embeddings.py
    │   └── driven/                   # Outbound
    │       ├── supabase/
    │       │   ├── conversation_repository.py
    │       │   └── vector_store.py
    │       ├── openai/
    │       │   ├── embeddings_service.py
    │       │   └── llm_service.py
    │       ├── liveavatar/
    │       │   └── avatar_client.py
    │       └── in_memory/            # Test doubles
    │           ├── conversation_repository.py
    │           └── fake_llm_service.py
    ├── config/
    │   ├── settings.py               # Pydantic settings
    │   ├── dependencies.py           # Dependency injection
    │   └── logging.py
    └── main.py                       # FastAPI bootstrap
```

#### Data Flow Example: Send Message

```
1. [REST Controller] POST /api/chat/conversations/{id}/messages
   ↓
2. [Driver Adapter] Parse request → SendMessageCommand
   ↓
3. [Application Handler] SendMessageHandler.execute(command)
   ├─→ [Driven Port] RAGService.retrieve_context(query)
   │   └→ [Driven Adapter] SupabaseVectorStore (cosine similarity search)
   ├─→ [Driven Port] LLMService.generate_response(context, query)
   │   └→ [Driven Adapter] OpenAIClient (GPT-4o-mini)
   ├─→ [Domain] Conversation.add_message(message)
   └─→ [Driven Port] ConversationRepository.save(conversation)
       └→ [Driven Adapter] SupabaseConversationRepository
   ↓
4. [Driver Adapter] Return MessageDTO as JSON
```

### Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **API Framework** | FastAPI 0.110+ | Async support, type hints, OpenAPI docs, proven in Purrfect Hire |
| **Language** | Python 3.11+ | Your primary backend language, rich AI/ML ecosystem |
| **Database** | Supabase (PostgreSQL 15+) | PostgreSQL expertise + pgvector for embeddings, managed service |
| **Vector Search** | pgvector extension | Native PostgreSQL integration, proven at scale |
| **LLM Provider** | OpenAI API | GPT-4o-mini for cost-effective Q&A, fallback to 3.5-turbo |
| **Embeddings** | text-embedding-3-small | 1536-dim, cost-effective, sufficient accuracy |
| **Avatar Service** | LiveAvatar.com API | Third-party service, token-based integration |
| **Testing** | pytest + pytest-asyncio | Python standard, async support |
| **Architecture Tests** | custom pytest plugin | Enforce dependency rules (domain → app → infra) |
| **CI/CD** | GitHub Actions | Free for public repos, Docker build + deploy to Digital Ocean |
| **Deployment** | Digital Ocean Droplet | Your proven platform, Docker Compose orchestration |
| **Monitoring** | Sentry (errors) + Prometheus (metrics) | Standard observability stack |
| **API Documentation** | FastAPI auto-generated + Swagger UI | Zero-effort OpenAPI docs |

### Integration Points

#### External APIs

1. **OpenAI API**
   - Endpoints: `/v1/embeddings`, `/v1/chat/completions`
   - Authentication: Bearer token (`OPENAI_API_KEY`)
   - Rate Limits: 10,000 TPM (tokens per minute) for embeddings, 90,000 TPM for completions
   - Error Handling: Exponential backoff on 429, circuit breaker on 500/503

2. **LiveAvatar.com API**
   - Endpoint: `/v1/token` (adjust to actual)
   - Authentication: API key header
   - Rate Limits: TBD (check LiveAvatar docs)
   - Fallback: Static avatar image if service unavailable

3. **Supabase**
   - PostgreSQL connection: `postgresql://user:pass@db.supabase.co:5432/postgres`
   - REST API: `https://yourproject.supabase.co/rest/v1/`
   - Realtime: WebSocket for live updates (optional future feature)

#### Database Schema

**Conversations Table**
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_session_id ON conversations(session_id);
```

**Messages Table**
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
```

**Embeddings Table**
```sql
CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL CHECK (source_type IN ('cv', 'project', 'content')),
    source_id VARCHAR(255) NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_embeddings_embedding ON embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_embeddings_source ON embeddings(source_type, source_id);
```

**Avatar Sessions Table**
```sql
CREATE TABLE avatar_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    ip_address INET,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_avatar_sessions_expires_at ON avatar_sessions(expires_at);
```

### Security & Privacy

#### Authentication & Authorization
- **Public Endpoints**: No auth required for chatbot (demo portfolio)
- **Rate Limiting**: 
  - Chatbot: 30 requests per IP per hour
  - Avatar token: 10 requests per IP per hour
- **CORS**: Whitelist portfolio frontend domain only

#### Data Privacy
- **No PII Collection**: Chatbot conversations not linked to real users
- **Session Isolation**: Conversations identified by anonymous session ID (UUID)
- **Data Retention**: 
  - Conversations: 30 days (auto-delete)
  - Logs: 7 days
  - Embeddings: Permanent (static knowledge base)
- **API Keys**: Environment variables only, never in code/logs

#### Input Validation
- **Message Length**: Max 1000 characters
- **SQL Injection**: Parameterized queries via SQLAlchemy ORM
- **Prompt Injection**: System prompt isolation, input sanitization

#### Secrets Management
```bash
# .env (never committed)
OPENAI_API_KEY=sk-...
LIVEAVATAR_API_KEY=la-...
SUPABASE_URL=https://...
SUPABASE_KEY=eyJh...
DATABASE_URL=postgresql://...
SENTRY_DSN=https://...
```

---

## 5. Risks & Roadmap

### Phased Rollout

#### MVP (v0.1) - 2 weeks
**Goal**: Proof of concept with core RAG chatbot

**Deliverables**:
- ✅ Project structure (Clean + DDD + Hexagonal folders)
- ✅ Domain models: Conversation, Message entities
- ✅ Basic RAG: CV embedding + semantic search
- ✅ OpenAI integration (GPT-4o-mini)
- ✅ Single REST endpoint: `POST /api/chat/messages`
- ✅ In-memory repository (no database)
- ✅ 10 benchmark questions with >80% accuracy

**Success Criteria**: Can answer "What companies has Richard worked for?" correctly

#### v1.0 - 4 weeks
**Goal**: Production-ready chatbot + avatar integration

**Deliverables**:
- ✅ Supabase PostgreSQL + pgvector setup
- ✅ Full conversation management (session-based)
- ✅ LiveAvatar.com token generation endpoint
- ✅ WebSocket for avatar state sync
- ✅ Comprehensive test suite (unit + integration)
- ✅ Architecture tests (dependency rule enforcement)
- ✅ GitHub Actions CI/CD
- ✅ Digital Ocean deployment
- ✅ API documentation (Swagger UI)
- ✅ Error monitoring (Sentry)

**Success Criteria**: 
- RAG accuracy >= 90%
- P95 latency < 500ms
- Zero-downtime deployment

#### v1.1 - 2 weeks post-launch
**Goal**: Optimization and observability

**Deliverables**:
- ✅ Prometheus metrics (request counts, latencies, token usage)
- ✅ Grafana dashboard
- ✅ Embedding cache (reduce OpenAI costs)
- ✅ Response streaming (SSE for real-time typing effect)
- ✅ Enhanced benchmark suite (50 questions)

#### v2.0 - Future (optional)
**Goal**: Advanced features

**Potential Features**:
- Multi-turn conversation memory (RAG over conversation history)
- Voice input/output (Web Speech API + TTS)
- Project-specific chatbots (isolated knowledge bases)
- Admin panel for knowledge base management
- A/B testing framework for prompt optimization

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **OpenAI API Rate Limits** | Medium | High | Implement request queue, use caching, monitor token usage, budget alerts |
| **Supabase Downtime** | Low | High | Connection pooling, retry logic, health checks, fallback to in-memory for dev |
| **LiveAvatar.com Service Unavailable** | Medium | Medium | Graceful degradation to static avatar image, cache valid tokens |
| **RAG Accuracy Below 90%** | Medium | Medium | Iterative prompt engineering, expand knowledge base, adjust chunk size/overlap |
| **High Latency (>500ms)** | Low | Medium | Async operations, embedding cache, connection pooling, CDN for static assets |
| **Over-Budget on OpenAI** | Medium | Low | Set spending limits, use cheaper models (3.5-turbo fallback), cache responses |
| **Dependency Rule Violations** | Low | Medium | Automated architecture tests in CI, pre-commit hooks, code review checklist |
| **Security Vulnerability** | Low | High | OWASP Top 10 checklist, dependency scanning (Dependabot), input validation |

### Cost Estimation (Monthly)

**OpenAI API**:
- Embeddings: ~10k chunks × $0.00002 per 1k tokens = $0.20 one-time
- Chat completions: 10k queries × 1k tokens × $0.0001 per 1k tokens = $1.00/month
- **Total**: ~$1.20/month (negligible for portfolio)

**LiveAvatar.com**: TBD (check pricing, likely free tier sufficient)

**Supabase**: Free tier (up to 500MB database, sufficient for portfolio)

**Digital Ocean**: $12/month (basic droplet, 2GB RAM)

**Sentry**: Free tier (5k events/month)

**Total Estimated**: ~$15/month

---

## 6. Testing Strategy

### Unit Tests (Domain + Application Layers)

**Coverage Target**: >= 85%

**Example Test Cases**:
```python
# tests/domain/chatbot/test_conversation.py
def test_conversation_add_message_increases_message_count():
    conversation = Conversation.create(session_id="test-123")
    message = Message.create_user_message("Hello")
    
    conversation.add_message(message)
    
    assert conversation.message_count == 1

def test_conversation_cannot_add_empty_message():
    conversation = Conversation.create(session_id="test-123")
    
    with pytest.raises(ValueError, match="Message content cannot be empty"):
        conversation.add_message(Message.create_user_message(""))

# tests/application/chatbot/test_send_message_handler.py
@pytest.mark.asyncio
async def test_send_message_retrieves_context_and_generates_response():
    # Arrange
    fake_rag = FakeRAGService(mock_context="Richard worked at Purrfect Hire")
    fake_llm = FakeLLMService(mock_response="He worked at Purrfect Hire as Technical Lead")
    handler = SendMessageHandler(rag=fake_rag, llm=fake_llm, repo=InMemoryRepo())
    
    # Act
    result = await handler.execute(SendMessageCommand(
        conversation_id="conv-1",
        message="Where did Richard work?"
    ))
    
    # Assert
    assert "Purrfect Hire" in result.response
    assert fake_rag.was_called_with("Where did Richard work?")
    assert fake_llm.was_called
```

### Integration Tests

**Coverage Target**: >= 70%

**Example Test Cases**:
```python
# tests/integration/test_chatbot_api.py
@pytest.mark.asyncio
async def test_send_message_returns_relevant_response(test_client, seeded_embeddings):
    # Arrange
    response = await test_client.post("/api/chat/conversations", json={})
    conversation_id = response.json()["id"]
    
    # Act
    response = await test_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "What AI models has Richard used?"}
    )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "OpenAI" in data["response"] or "GPT" in data["response"]
    assert len(data["sources"]) > 0
```

### Architecture Tests

**Enforce Clean Architecture Rules**:
```python
# tests/architecture/test_dependency_rules.py
def test_domain_has_no_external_dependencies():
    """Domain layer must not import from application or infrastructure"""
    domain_modules = get_all_modules_in_package("src.domain")
    
    for module in domain_modules:
        imports = get_imports(module)
        assert not any(imp.startswith("src.application") for imp in imports)
        assert not any(imp.startswith("src.infrastructure") for imp in imports)

def test_application_does_not_import_infrastructure():
    """Application layer must not import from infrastructure"""
    app_modules = get_all_modules_in_package("src.application")
    
    for module in app_modules:
        imports = get_imports(module)
        assert not any(imp.startswith("src.infrastructure") for imp in imports)
```

### RAG Evaluation Suite

**Benchmark Dataset**:
```python
# tests/rag/benchmark_questions.json
[
  {
    "question": "What companies has Richard worked for?",
    "expected_entities": ["Purrfect Hire", "Indra", "Sonrisas y Salud"],
    "category": "employment_history"
  },
  {
    "question": "Has he built AI systems?",
    "expected_keywords": ["RAG", "chatbot", "OpenAI", "LangChain"],
    "category": "technical_skills"
  },
  {
    "question": "What's his experience with Clean Architecture?",
    "expected_entities": ["FastAPI", "Purrfect Hire ATS"],
    "category": "architecture_patterns"
  }
]
```

**Evaluation Script**:
```python
# tests/rag/evaluate_rag_system.py
@pytest.mark.eval
@pytest.mark.asyncio
async def test_benchmark_accuracy():
    questions = load_benchmark_questions()
    results = []
    
    for q in questions:
        response = await chatbot.ask(q["question"])
        score = evaluate_response(response, q["expected_entities"], q["expected_keywords"])
        results.append(score)
    
    avg_accuracy = sum(results) / len(results)
    assert avg_accuracy >= 0.90, f"RAG accuracy {avg_accuracy:.2%} below 90% threshold"
```

---

## 7. Deployment & Operations

### CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install poetry
      - run: poetry install
      - run: poetry run pytest --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v3

  architecture-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install poetry
      - run: poetry install
      - run: poetry run pytest tests/architecture/ -v

  build-and-deploy:
    needs: [test, architecture-tests]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/build-push-action@v4
        with:
          push: true
          tags: registry.digitalocean.com/portfolio/backend:latest
      - name: Deploy to Digital Ocean
        run: |
          ssh deploy@${{ secrets.DO_SERVER_IP }} << 'EOF'
            docker pull registry.digitalocean.com/portfolio/backend:latest
            docker-compose up -d --no-deps backend
          EOF
```

### Docker Setup

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

COPY . .

CMD ["poetry", "run", "uvicorn", "src.infrastructure.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LIVEAVATAR_API_KEY=${LIVEAVATAR_API_KEY}
      - SENTRY_DSN=${SENTRY_DSN}
    depends_on:
      - postgres

  postgres:
    image: ankane/pgvector:latest
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### Monitoring & Alerts

**Sentry Configuration**:
```python
# src/infrastructure/config/sentry.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.ENVIRONMENT,
    traces_sample_rate=0.1,
    integrations=[FastApiIntegration()],
)
```

**Health Check Endpoint**:
```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "dependencies": {
            "database": await check_db_connection(),
            "openai": await check_openai_api(),
            "liveavatar": await check_liveavatar_api(),
        }
    }
```

---

## Appendix A: API Endpoints Specification

### Chatbot Endpoints

#### POST /api/chat/conversations
Create new conversation session.

**Request**: None (session ID auto-generated)

**Response**:
```json
{
  "id": "conv-uuid-here",
  "session_id": "sess-uuid-here",
  "started_at": "2026-03-16T10:00:00Z"
}
```

#### POST /api/chat/conversations/{conversation_id}/messages
Send message in conversation.

**Request**:
```json
{
  "content": "What companies has Richard worked for?"
}
```

**Response**:
```json
{
  "id": "msg-uuid-here",
  "role": "assistant",
  "content": "Richard has worked for three companies: Purrfect Hire (May 2025 - Present) as Technical Lead, Indra (Feb 2022 - May 2025) progressing from Process Management to Project Lead, and Sonrisas y Salud (Feb 2021 - May 2021) as a freelance developer.",
  "sources": [
    {"type": "cv", "section": "Work Experience", "confidence": 0.95}
  ],
  "created_at": "2026-03-16T10:01:00Z"
}
```

#### GET /api/chat/conversations/{conversation_id}
Retrieve conversation history.

**Response**:
```json
{
  "id": "conv-uuid-here",
  "messages": [
    {"role": "user", "content": "...", "created_at": "..."},
    {"role": "assistant", "content": "...", "sources": [...], "created_at": "..."}
  ]
}
```

### Avatar Endpoints

#### POST /api/avatar/token
Generate LiveAvatar.com session token.

**Request**:
```json
{
  "duration_minutes": 30
}
```

**Response**:
```json
{
  "token": "eyJhbGc...",
  "expires_at": "2026-03-16T10:30:00Z",
  "websocket_url": "wss://avatar.liveavatar.com/session/..."
}
```

**Error Response (429 - Rate Limited)**:
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 3600
}
```

---

## Appendix B: Knowledge Base Seeding Script

```python
# scripts/seed_embeddings.py
"""
Seed knowledge base with CV and project embeddings.
Run once during deployment, then on content updates.
"""

import asyncio
from src.application.ports.embeddings_service import IEmbeddingsService
from src.infrastructure.adapters.openai.embeddings_service import OpenAIEmbeddingsService
from src.infrastructure.adapters.supabase.vector_store import SupabaseVectorStore

async def seed_cv_embeddings():
    embeddings_service = OpenAIEmbeddingsService()
    vector_store = SupabaseVectorStore()
    
    # Load CV content
    cv_chunks = [
        {"text": "Richard worked at Purrfect Hire from May 2025...", "metadata": {"section": "Purrfect Hire"}},
        {"text": "At Indra, Richard led a technical audit team...", "metadata": {"section": "Indra"}},
        # ... more chunks
    ]
    
    for chunk in cv_chunks:
        embedding = await embeddings_service.embed(chunk["text"])
        await vector_store.store(
            source_type="cv",
            source_id=chunk["metadata"]["section"],
            chunk_text=chunk["text"],
            embedding=embedding,
            metadata=chunk["metadata"]
        )
    
    print(f"Seeded {len(cv_chunks)} CV chunks")

if __name__ == "__main__":
    asyncio.run(seed_cv_embeddings())
```

---

## Appendix C: Glossary

- **RAG**: Retrieval-Augmented Generation - AI pattern combining semantic search with LLM generation
- **Aggregate**: DDD pattern defining transaction/consistency boundary
- **Port**: Hexagonal architecture interface defining boundary
- **Adapter**: Hexagonal architecture implementation of a port
- **Driver Port**: Inbound interface (how world uses app)
- **Driven Port**: Outbound interface (how app uses world)
- **Entity**: DDD object with identity
- **Value Object**: DDD immutable object defined by attributes
- **Use Case**: Application layer service implementing business operation
- **pgvector**: PostgreSQL extension for vector similarity search
- **Embedding**: Vector representation of text for semantic similarity

---

**END OF PRD**

---

## Next Steps

1. **Review & Feedback**: Get stakeholder (you) approval on scope and architecture
2. **Repository Setup**: Initialize Git repo with folder structure
3. **Environment Setup**: Configure Supabase, OpenAI API, Digital Ocean
4. **Sprint Planning**: Break v0.1 MVP into 2-week sprint tasks
5. **Development Start**: Begin with domain models (entities, value objects)

**Questions for Clarification**:
1. LiveAvatar.com API specifics - do you have docs/credentials yet?
2. Preferred deployment frequency - continuous deployment or manual releases?
3. OpenAI budget cap - hard limit on monthly spend?
4. Timeline pressure - is 4 weeks for v1.0 realistic given other commitments?
