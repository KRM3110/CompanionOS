<h1 align="center"> CompanionOS </h1>

<p align="center">
  An Advanced Agentic Workspace Platform for Multi-Modal RAG, Automated Web Research, Structured Memory Extraction, and Robust AI Safety Guardrails.
</p>

<p align="center">
  <img alt="Build" src="https://img.shields.io/badge/Build-Passing-brightgreen?style=for-the-badge">
  <img alt="Issues" src="https://img.shields.io/badge/Issues-0%20Open-blue?style=for-the-badge">
  <img alt="Contributions" src="https://img.shields.io/badge/Contributions-Welcome-orange?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge">
</p>
<!-- 
  **Note:** These are static placeholder badges. Replace them with your project's actual badges.
  You can generate your own at https://shields.io
-->

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Tech Stack & Architecture](#-tech-stack--architecture)
- [Project Structure](#-project-structure)
- [Environment Variables](#-environment-variables)
- [Getting Started](#-getting-started)
- [Usage](#-usage)
- [Contributing](#-contributing)
- [License](#-license)

---

## ⭐ Overview

### Hook
**CompanionOS** is an intelligent, containerized developer workspace and documentation engine that processes local knowledge bases, synthesizes multi-step web research, and maintains long-term contextual memory to streamline AI-driven workflows.

### The Problem
> Modern software development requires developers to continuously context-switch between local codebases, browser-based technical documentation search, and conversational AI tools. Maintaining project context inside narrow prompt windows is fragile: critical context is lost, manual search consumes hours, local files remain disconnected, and untrusted prompts expose systems to injection exploits. Developers need an unified local OS companion that indexes knowledge securely and processes multi-modal documentation without friction.

### The Solution
CompanionOS merges custom persona agents (Coach, Mentor, Calm) with active workspace sessions to solve the developer context crisis. Powered by an asynchronous FastAPI backend and an interactive Next.js interface, the platform reads documents (`.pdf`, `.docx`, `.txt`, `.md`), embeds them in a local ChromaDB instance, dynamically searches the live web using DuckDuckGo, extracts core developer memories, and formats output structures while applying rigorous real-time security scanning. 

```
                                  +-----------------------+
                                  |   Next.js Frontend    |
                                  | (Chat, Workspaces)    |
                                  +-----------+-----------+
                                              |
                                              | REST / SSE
                                              v
                                  +-----------------------+
                                  |    FastAPI Backend    |
                                  +-----+-----+-----+-----+
                                        |     |     |
      +---------------------------------+     |     +---------------------------------+
      |                                       |                                       |
      v                                       v                                       v
+-----+-----+                           +-----+-----+                           +-----+-----+
| Vector DB | <--- (Parsers, Embedder)  | Relational| <--- (Alembic Schema)     | Agent Core| <--- (Google Gemini,
|  Chroma   |                           |  SQLite   |                           |  MX1 Mem) |       DuckDuckGo API)
+-----------+                           +-----------+                           +-----------+
```

---

## ✨ Key Features

### 📁 Multi-Modal Document Workspace
- **Context Isolation:** Create distinct workspaces that logically isolate vector databases, workspace tools, and document schemas.
- **Dynamic Parsers:** Ingest and parse `.pdf`, `.docx`, `.txt`, and `.md` formats, executing character-level overlapping chunking to retain code context.
- **Persistent Vector Retrieval:** Stores chunked vector embeddings locally in ChromaDB and automatically formats relevant metadata badges in the visual interface.

### 🔍 Deep Web Research Agent
- **Iterative Search & Deduplication:** Plan searches using a multi-step research planner, call the DuckDuckGo search API, and deduplicate matching source links.
- **Automated Report Builder:** Consolidates raw internet results, formats Markdown references, and outputs analytical reports directly in the user view.
- **SSE Stream Execution:** Stream active agent thoughts, searches, and planner events directly to the UI in real-time.

### 🧠 MX1 Memory Extraction Lifecycle
- **Conversational Memory Synthesis:** Extracts critical facts, user requirements, and persistent context from the chat stream using schema-validated extraction templates.
- **Continuous Alignment:** Updates the agent's system prompt dynamically behind the scenes to keep the conversation continuously aligned to current goals.

### 🛡️ Multi-Tier Security Guardrails
- **Prompt Injection Defense:** Scans incoming payloads using structural regex filters and validation mechanisms before sending requests to the LLM.
- **Content Sanitizer:** Intercepts and cleans sensitive signatures or malicious payload executions.

### ⚙️ Customizable Modes & Personas
- **Dynamic Policy Loader:** Run-time loading of policies (Response, Memory, Safety, and Tool availability) based on active modes (`focus.json`, `safe.json`, `research.json`).
- **Personality Personas:** Pivot the AI’s personality instantly between predefined modes (`mentor.json`, `coach.json`, `calm.json`).

### 🔔 Session Alerts System
- **LLM-Triggered Alerts:** An automated background alert-extractor tool parses conversational intent to generate, pause, or complete tracking alerts.

---

## 🛠️ Tech Stack & Architecture

CompanionOS implements a modular component-based microservices architecture, isolating the static Next.js frontend, persistent ChromaDB collections, and the high-throughput FastAPI engine.

| Technology | Category | Verified Purpose | Why it was Chosen |
| :--- | :--- | :--- | :--- |
| **FastAPI** | Backend | High-performance asynchronous API services and endpoint routing | Provides native async task support, automatic OpenAPI docs, and clean dependency injection. |
| **Next.js (v14.2.35)** | Frontend | React framework for server-rendered user interface layouts | Delivers optimized builds, unified routing, and structured component rendering. |
| **Tailwind CSS (v4)** | CSS Engine | Modern utility-first interface styling and layout design | Allows rapid design customization and high performance without runtime CSS overhead. |
| **ChromaDB** | Vector Store | Local persistent vector storage and cosine similarity searches | Compact embedded vector store running directly in Python process memory. |
| **Google Gemini (LangChain Client)** | LLM Provider | Primary language model executing backend logic via Gemini API | Advanced multi-modal understanding, high-context recall, and cost-effective text generation. |
| **DuckDuckGo Search** | Search Integration | Sync-based web search for external agent planning | Fast, anonymous search API requiring no authentication keys. |
| **Alembic** | Database Migration | Database schema schema-version tracking and migrations | Guarantees deterministic relational schema transitions for database connections. |
| **Docker / Compose** | Infrastructure | Container orchestration and environmental consistency | Eliminates localized environment installation issues across host operating systems. |

---

## 📁 Project Structure

```
KRM3110-CompanionOS/
├── 📄 docker-compose.yml             # Orchestrates frontend and backend container configurations
├── 📄 Read Me.md                     # Project documentation
├── 📄 .gitignore                     # Git tracking exclusions
├── 📁 personas/                      # JSON-based personality configuration definitions
│   ├── 📄 mentor.json               # Developer-focused mentor persona profiles
│   ├── 📄 coach.json                # Goal-oriented performance coach settings
│   └── 📄 calm.json                 # De-escalated, neutral assistance persona
├── 📁 frontend/                      # Next.js web application core files
│   ├── 📄 package.json              # Web app dependencies and run scripts
│   ├── 📄 package-lock.json         # Lockfile for exact npm builds
│   ├── 📄 next.config.js            # Configuration for optimization and api rewrites
│   ├── 📄 tsconfig.json             # Static TypeScript typing guidelines
│   ├── 📄 postcss.config.js         # Post-processing CSS loader configurations
│   ├── 📄 tailwind.config.ts        # Tailwind CSS theme bindings
│   ├── 📄 Dockerfile                # Production multi-stage image builder for UI
│   ├── 📁 app/                      # Next.js app directory
│   │   ├── 📄 globals.css           # Global Tailwind stylings
│   │   ├── 📄 layout.tsx            # Main HTML wrapper containing metadata bindings
│   │   └── 📄 page.tsx              # Interactive application landing page interface
│   ├── 📁 lib/                      # Base client execution functions
│   │   ├── 📄 api.ts                # TypeScript endpoints layer communicating with FastAPI
│   │   └── 📄 types.ts              # Global TypeScript structural types
│   ├── 📁 hooks/                     # Custom React context hooks
│   │   └── 📄 useChatSession.ts     # Standard Chat interaction manager hook
│   └── 📁 components/                # Modular React user interface blocks
│       ├── 📄 ChatWindow.tsx        # Standard chat log stream view
│       ├── 📄 WorkspacePanel.tsx    # Left panel containing active workspaces and documents
│       ├── 📄 Toast.tsx             # Interactive application notification badges
│       ├── 📄 RAGSourceBadge.tsx    # Interactive vector-source metadata indicator
│       ├── 📄 AlertsPanel.tsx       # Live status visual tracking tool panel
│       └── 📄 WebSourceBadge.tsx    # Live web resource citation tracker
└── 📁 backend/                       # Python FastAPI backend core
    ├── 📄 Dockerfile                # Custom slim Python package image builder
    ├── 📄 requirements.txt          # PIP dependencies index
    ├── 📄 alembic.ini               # Relational migration setup configuration
    ├── 📁 alembic/                  # Relational database migration scripts
    │   ├── 📄 env.py                # Database context loading pipeline
    │   ├── 📄 script.py.mako        # Autogeneration templates
    │   └── 📁 versions/             # Migration versions
    │       └── 📄 0001_baseline.py  # Primary relational schema deployment
    └── 📁 app/                      # FastAPI engine source files
        ├── 📄 main.py               # Main API launch controller and middleware router
        ├── 📄 config.py             # Singleton application configurations
        ├── 📄 pipeline.py           # Message flow pipeline execution
        ├── 📄 prompt_builder.py     # Assembles contextual system instructions
        ├── 📄 llm_client.py         # Google Gemini Langchain execution engine
        ├── 📄 state.py              # Active execution parameter blocks
        ├── 📄 chat_jobs.py          # Background worker tasks executor
        ├── 📄 memory_extractor.py   # MX1 schema-based parser
        ├── 📄 utils.py              # Parsing helpers (TOON/YAML formatting)
        ├── 📁 tools/                # Extensible integration tools framework
        │   ├── 📄 __init__.py       # Tools package entry definitions
        │   ├── 📄 bootstrap.py      # Core tools builder setup
        │   ├── 📄 registry.py       # Plugin lookup coordinator
        │   ├── 📄 base.py           # Universal BaseTool class definition
        │   ├── 📄 runner.py         # Handles running enabled tool workflows
        │   └── 📁 alerts/           # Core background context-alert engine
        │       ├── 📄 __init__.py
        │       ├── 📄 alert_extractor.py # Extract alert values via LLM prompts
        │       ├── 📄 alert_service.py # Core database state management for alerts
        │       ├── 📄 tool.py       # Implements primary ToolPlugin class 
        │       └── 📁 prompts/      # Alert-specific target prompt directions
        │           ├── 📄 system.txt # Guard rails for JSON output formatting
        │           └── 📄 template.txt # Template processing format guidelines
        ├── 📁 routes/               # Modular REST endpoints
        │   ├── 📄 __init__.py       
        │   ├── 📄 health.py         # Liveness/readiness router check
        │   ├── 📄 chat.py           # Conversation engine stream management
        │   ├── 📄 sessions.py       # Session CRUD endpoint routes
        │   ├── 📄 workspaces.py     # Document store workspaces controller
        │   ├── 📄 research.py       # DuckDuckGo multi-agent query endpoints
        │   ├── 📄 security.py       # Injection security scanning services
        │   ├── 📄 modes.py          # Environment system layout configurations
        │   ├── 📄 alerts.py         # Alarm scheduling controller API
        │   ├── 📄 tools.py          # Tool listing API endpoint
        │   ├── 📄 memory.py         # Long-term fact persistence routing
        │   └── 📄 schemas.py        # Marshaled request/response validators
        ├── 📁 rag/                  # RAG (Retrieval-Augmented Generation) pipeline
        │   ├── 📄 __init__.py       
        │   ├── 📄 document_store.py # Identifies MIME signatures and directories
        │   ├── 📄 parsers.py        # PDF, DOCX, TXT splitters and segmenters
        │   ├── 📄 embedder.py       # Wraps client vector transformers
        │   ├── 📄 vector_store.py   # Manages ChromaDB collections
        │   └── 📄 rag_retriever.py  # Inject and format context strings into prompts
        ├── 📁 research/             # Multi-agent live search planners
        │   ├── 📄 __init__.py       
        │   ├── 📄 research_agent.py # Emits real-time SSE planner actions
        │   ├── 📄 web_searcher.py   # Deduplicated web searching actions
        │   ├── 📄 research_planner.py # Orchestrates steps for complex reports
        │   ├── 📄 report_builder.py # Renders unstructured data to rich reports
        │   └── 📄 research_db.py    # Logs search events
        ├── 📁 security/             # Security filtering mechanisms
        │   ├── 📄 __init__.py       
        │   ├── 📄 guard_db.py       # Stores logged attempts
        │   ├── 📄 sanitizer.py      # Removes command strings from prompts
        │   ├── 📄 injection_detector.py # Scans for exploitation signatures
        │   ├── 📄 llm_guard.py      # Master boundary scanner
        │   └── 📄 content_guard.py  # Filters outbound toxic structures
        ├── 📁 modes/                # Mode configurations
        │   ├── 📄 __init__.py       
        │   ├── 📄 schema.py         # Models defining constraints 
        │   ├── 📄 loader.py         # Locates and validates JSON policies
        │   └── 📁 data/             # System constraints structures
        │       ├── 📄 research.json # Policies for research actions
        │       ├── 📄 safe.json     # Strict validation filters
        │       └── 📄 focus.json    # Deep task-level optimization profiles
        ├── 📁 agents/               # Custom agent configuration directory
        │   └── 📄 __init__.py       
        ├── 📁 db/                   # Database operations layer
        │   ├── 📄 __init__.py       
        │   ├── 📄 connection.py     # SQLAlchemy connection session helper
        │   ├── 📄 sessions.py       # User interaction session state storage
        │   ├── 📄 workspaces.py     # Document workspace metadata storage
        │   ├── 📄 documents.py      # Source catalog and path registries
        │   ├── 📄 messages.py       # Persisted message history storage
        │   ├── 📄 summaries.py      # Historical summarization data maps
        │   ├── 📄 memory.py         # Persisted user-fact storage tables
        │   ├── 📄 tool_settings.py  # Fine-grained parameters
        │   ├── 📄 alerts.py         # Alarm triggers database layer
        │   └── 📄 chat_jobs.py      # Background worker job database tables
        └── 📁 prompts/              # System prompt and template directories
            ├── 📁 mx1/              # Memory extract directives
            │   ├── 📄 system.txt    
            │   └── 📄 schema.json   
            ├── 📁 research/         # Research planning directives
            │   ├── 📄 planner.txt   
            │   └── 📄 report_builder.txt 
            └── 📁 modes/            # Agent state prompts
                ├── 📄 research.txt  
                ├── 📄 focus.txt     
                └── 📄 safe.txt      
```

---

## 🔐 Environment Variables

Before starting the containers, set up the following environment variables in your `.env` file in the root directory.

| Variable Name | Required | Default Value | Purpose |
| :--- | :--- | :--- | :--- |
| `OLLAMA_MODEL` | Yes | `gemma2:27b` | Sets the processing model if leveraging localized inference engines. |
| `NEXT_PUBLIC_API_BASE_URL` | Yes | `http://localhost:8000` | Points the Next.js frontend application to the FastAPI backend host. |

---

## 🚀 Getting Started

Follow these steps to build and run CompanionOS on your local system.

### Prerequisites
Ensure your local machine has the following software installed:
- **Git** (to clone the repository)
- **Docker Engine** (version 20.10.0 or higher)
- **Docker Compose** (version 1.29.0 or higher)

---

### Step-by-Step Installation

#### 1. Clone the Codebase
Clone the project repository to your local computer:
```bash
git clone https://github.com/KRM3110/KRM3110-CompanionOS-a233ef0.git
cd KRM3110-CompanionOS-a233ef0
```

#### 2. Configure Environment Variables
Copy the root `.env.example` file to create your active `.env` configuration file:
```bash
cp .env.example .env
```
Ensure you edit this `.env` file to match your environment, verifying the value of `NEXT_PUBLIC_API_BASE_URL` is accessible from your browser.

#### 3. Run the Services using Docker Compose
Deploy CompanionOS directly using Docker Compose. This single command downloads images, builds the custom frontend/backend Dockerfiles, configures storage, and starts both services:
```bash
docker-compose up --build
```

#### 4. Apply Database Migrations
Once the containers are running, navigate to the backend container to apply the baseline Alembic database schema migrations:
```bash
docker-compose exec backend alembic upgrade head
```

#### 5. Verify the Installation
Open your browser and navigate to:
- **Interactive UI (Frontend):** `http://localhost:3000`
- **REST API Docs (FastAPI Backend Swagger):** `http://localhost:8000/docs`

---

## 🔧 Usage

### 1. Navigating the Workspace Panel
Inside the frontend dashboard, locate the **Workspace Panel** on the left side of the screen.
- Click **"Create Workspace"** to isolate a new research subject or codebase.
- Click **"Upload Document"** to upload technical `.pdf`, `.docx`, or `.md` files directly. This triggers the backend document parser, which populates the workspace collections in your local ChromaDB.

### 2. Conversing & Utilizing RAG Context
Type your messages directly in the **Chat Window**.
- When you ask questions about your documents, the system searches the database, retrieves relevant content, and injects context into the LLM prompt.
- The UI displays green **RAG Source Badges** indicating which parts of your documents were used to generate the answer.

### 3. Activating Deep Web Research
To research topics on the live web:
1. Open the Chat Mode drop-down menu and choose **Research Mode**.
2. Submit your research task (e.g., *"Research current architecture patterns for FastAPI microservices"*).
3. The **Research Planner** dynamically designs search steps and displays search logs using **Web Source Badges**.
4. The system outputs a structured Markdown report within the chat interface.

### 4. Setting Automatic Event Alerts
The background alert tool dynamically parses your messages. You can also view and track actions through the **Alerts Panel** on the right side of the interface to keep your projects on schedule:
- Ask the agent: *"Alert me to review API schemas in 10 minutes."*
- The background pipeline automatically creates a structured, trackable alert in your session database.

---

## 🤝 Contributing

We welcome contributions to improve CompanionOS! Your input helps make this project better for everyone.

### How to Contribute

1. **Fork the repository** - Click the 'Fork' button at the top right of this page
2. **Create a feature branch** 
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes** - Improve code, documentation, or features
4. **Test thoroughly** - Ensure all functionality works as expected
   ```bash
   # Run local tests depending on environment setup, e.g.:
   pytest backend/tests/
   ```
5. **Commit your changes** - Write clear, descriptive commit messages
   ```bash
   git commit -m 'Add: Amazing new feature that does X'
   ```
6. **Push to your branch**
   ```bash
   git push origin feature/amazing-feature
   ```
7. **Open a Pull Request** - Submit your changes for review

### Development Guidelines

- ✅ Follow the existing code style and conventions
- 📝 Add comments for complex logic and algorithms
- 🧪 Write tests for new features and bug fixes
- 📚 Update documentation for any changed functionality
- 🔄 Ensure backward compatibility when possible
- 🎯 Keep commits focused and atomic

### Ideas for Contributions

We're looking for help with:

- 🐛 **Bug Fixes:** Report and fix bugs
- ✨ **New Features:** Implement requested features from issues
- 📖 **Documentation:** Improve README, add tutorials, create examples
- 🎨 **UI/UX:** Enhance user interface and experience
- ⚡ **Performance:** Optimize code and improve efficiency
- 🌐 **Internationalization:** Add multi-language support
- 🧪 **Testing:** Increase test coverage
- ♿ **Accessibility:** Make the project more accessible

### Code Review Process

- All submissions require review before merging
- Maintainers will provide constructive feedback
- Changes may be requested before approval
- Once approved, your PR will be merged and you'll be credited

### Questions?

Feel free to open an issue for any questions or concerns. We're here to help!

---

## 📝 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for complete details.

### What this means:

- ✅ **Commercial use:** You can use this project commercially
- ✅ **Modification:** You can modify the code
- ✅ **Distribution:** You can distribute this software
- ✅ **Private use:** You can use this project privately
- ⚠️ **Liability:** The software is provided "as is", without warranty
- ⚠️ **Trademark:** This license does not grant trademark rights

---

<p align="center">Made with ❤️ by the CompanionOS Team</p>
<p align="center">
  <a href="#">⬆️ Back to Top</a>
</p>
