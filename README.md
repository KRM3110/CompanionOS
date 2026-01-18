CompanionOS (Avalon)

CompanionOS is a local, privacy-first AI companion system designed to run entirely on your machine.
Unlike cloud-based assistants, CompanionOS gives you full ownership of your data, memory, and tools while still behaving like a modern, intelligent assistant.

Avalon = Artificial Virtual Assistant with Logical and Operational Navigation

⸻

🚀 What Is CompanionOS?

CompanionOS is an AI operating loop, not just a chatbot.

It combines:
	•	Local LLM inference
	•	Structured long-term memory
	•	Persona-driven behavior
	•	Safety & quality enforcement
	•	Actionable tools (alerts/reminders)

All running offline using Docker.

⸻

🛠️ Tech Stack

Backend — The Brain
	•	Language: Python 3.11+
	•	Framework: FastAPI
	•	AI Engine: Ollama (local LLMs like Llama 3)
	•	Database: SQLite (local, file-based)
	•	Key Libraries:
	•	pydantic – strict schema validation
	•	requests – Ollama API communication
	•	pytz – timezone-aware scheduling

Frontend — The Face
	•	Framework: Next.js 14 (App Router)
	•	Language: TypeScript
	•	Styling: Tailwind CSS
	•	State Management: React hooks (useState, useEffect)

Infrastructure
	•	Docker Compose
	•	Backend (FastAPI)
	•	Frontend (Next.js)
	•	Ollama (LLM runtime)

Run everything with one command.

⸻

🏗️ Architecture Overview

The Core Loop
	1.	User sends a message from the frontend
	2.	FastAPI backend:
	•	Loads persona configuration
	•	Retrieves relevant memory (session + global)
	•	Builds a deterministic system prompt
	3.	Prompt is sent to Ollama
	4.	LLM generates a draft response
	5.	Draft is passed to the Judge Agent
	6.	Final response is returned to the user

⸻

🛡️ The Judge System (Safety Layer)

Every assistant response is reviewed by a Judge Agent:
	•	Ensures persona consistency
	•	Prevents unsafe or manipulative outputs
	•	Decides:
	•	PASS – response is acceptable
	•	REWRITE – minimal safe correction
	•	BLOCK – refuse with explanation

This guarantees quality + alignment, even with local models.

⸻

🔁 The Pipeline (Post-Chat Intelligence)

After each chat turn, a background pipeline runs:

🧠 Memory Agent (MX1)
	•	Extracts stable user facts and preferences
	•	Stores them as structured memory
	•	Uses confidence thresholds to avoid noise
	•	Updates session summaries every N messages

🛠️ Tools Agent
	•	Scans conversation for actionable intent
	•	Example:
“Remind me tomorrow to apply to 3 companies”
	•	Converts intent into structured tool actions

⸻

⏰ Alert System (Tools MVP)

The first implemented tool is in-app alerts:
	1.	Extraction
	•	LLM detects time-based or task-based intent
	2.	Storage
	•	Python calculates exact due_at
	•	Alert stored in SQLite
	3.	Notification
	•	Frontend polls backend periodically
	•	When alert is due → toast notification
	4.	User Control
	•	Acknowledge or dismiss alerts from UI

⸻

✨ Key Features
	•	🏠 Local & Private
No data leaves your machine. No cloud APIs.
	•	🧠 Long-Term Memory
Remembers goals, preferences, and plans across sessions.
	•	🎭 Personas
Switch personalities (Coach, Mentor, Calm) via config files.
	•	⏰ Active Tools
Alerts & reminders extracted directly from conversation.
	•	🛡️ Self-Correction
Judge agent enforces safety and persona consistency.
	•	📦 One-Command Setup
Fully dockerized for easy onboarding.




▶️ Running CompanionOS

Prerequisites
	•	Docker
	•	Docker Compose
	•	Ollama installed locally

Start Everything

🎯 Project Goals
	•	Build a sovereign AI companion
	•	Avoid cloud dependency and vendor lock-in
	•	Provide a framework for:
	•	Personas
	•	Memory
	•	Tools
	•	Local agents

This is designed as a foundation, not a one-off demo.

⸻

🔮 Future Work
	•	More tools (calendar, tasks, notes)
	•	Plugin-style tool marketplace
	•	Better scheduling & background workers
	•	Multi-agent routing
	•	Mobile UI
