🚀 CompanionOS (Avalon)

Your AI. Your machine. Your rules.

CompanionOS is a local-first AI companion platform that turns a large language model into a persistent, goal-aware digital partner — not just a chatbot.

Unlike cloud AI tools that forget everything and control your data, CompanionOS runs entirely on your machine, remembers what matters to you, and can take real action (like reminders and alerts) — all without sending your data anywhere.

Avalon stands for

Artificial Virtual Assistant with Logical and Operational Navigation

⸻

✨ Why CompanionOS Exists

Most AI assistants today are:
	•	Stateless
	•	Cloud-dependent
	•	Disposable after each chat
	•	Unsafe to trust with personal context

CompanionOS is built to answer a different question:

What if your AI actually remembered you, respected boundaries, and helped you execute — privately?

⸻

🧠 What Makes This Different

CompanionOS is not a chatbot.
It’s an AI operating loop.

It combines:
	•	🏠 Local LLMs (via Ollama)
	•	🧠 Structured long-term memory
	•	🎭 Persona-driven behavior
	•	🛡️ A built-in safety & quality judge
	•	🛠️ Actionable tools (alerts & reminders)
	•	🔁 Post-chat intelligence pipeline

All running offline, orchestrated with Docker.

⸻

⚙️ How It Works (High Level)

The Core Loop
	1.	You send a message from the UI
	2.	The backend:
	•	Loads your persona
	•	Pulls relevant memory
	•	Builds a deterministic system prompt
	3.	A local LLM generates a response
	4.	A Judge Agent reviews it for safety & alignment
	5.	The final response is returned
	6.	A background pipeline extracts memory & tools

This loop runs every message.

⸻

🛡️ The Judge System (Built-In Safety)

Every assistant response is reviewed by a second AI agent before you see it.

The Judge:
	•	Enforces persona consistency
	•	Blocks manipulative or unsafe behavior
	•	Automatically rewrites risky responses

Verdicts:
	•	PASS → show response
	•	REWRITE → safe correction
	•	BLOCK → refusal with explanation

This keeps the system trustworthy, even with local models.

⸻

🧠 Long-Term Memory (Not Prompt Stuffing)

CompanionOS doesn’t just shove old messages into prompts.

Instead, a Memory Agent:
	•	Extracts stable facts (goals, preferences, plans)
	•	Stores them structurally in SQLite
	•	Applies confidence thresholds to avoid noise
	•	Updates session summaries automatically

Your AI actually remembers — cleanly.

⸻

⏰ Tools That Act (Alerts MVP)

You can say things like:

“Remind me tomorrow to apply to 3 companies.”

CompanionOS will:
	1.	Detect intent using an LLM
	2.	Convert it into a structured alert
	3.	Store it locally
	4.	Notify you via the UI when it’s due
	5.	Let you acknowledge or dismiss it

No plugins. No cloud. No hacks.

⸻

🎭 Personas (Behavior as Config)

Personality isn’t hardcoded.

Personas are config files:
	•	Coach
	•	Mentor
	•	Calm

Each persona defines:
	•	Tone
	•	Strictness
	•	Empathy
	•	Memory behavior
	•	Response format

Switch personas → behavior changes instantly.

⸻

🛠️ Tech Stack

Backend
	•	Python 3.11+
	•	FastAPI
	•	Ollama (Llama 3, local inference)
	•	SQLite
	•	Modular agents & tool system

Frontend
	•	Next.js 14
	•	TypeScript
	•	Tailwind CSS
	•	Minimal, functional UI

Infrastructure
	•	Docker Compose
	•	One command to run everything
