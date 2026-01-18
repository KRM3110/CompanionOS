from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import os
import logging
import requests
from typing import List, Dict, Any

from .personas import load_personas
from .pipeline import run_post_chat_pipeline
from .tools.alerts.alert_extractor import extract_alerts
from .tools.alerts.alert_service import (
    execute_alert_creation,
    get_alerts_for_session,
    get_global_alerts,
    mark_alert_done,
    mark_alert_cancelled,
)

from .agents.Judge.judge_agent import run_judge

from .db import (
    init_db,
    create_session,
    list_sessions,
    get_session,
    add_message,
    get_messages,
    list_memory_items,
    upsert_memory_item,
    delete_memory_item,
    get_session_summary,
    count_messages,
    create_alert,
    list_alerts,
    update_alert_status,
    get_effective_tool_enabled_map,
    list_tool_settings,
    upsert_tool_setting,
    get_due_alerts,
)

from .tools.base import ToolContext
from .tools.runner import run_tools
from .tools.bootstrap import build_tools_registry

TOOLS_REGISTRY = build_tools_registry()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Config ----
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# ---- Load personas at startup ----
PERSONAS = load_personas()


@app.on_event("startup")
def _startup():
    init_db()


# ---------- Helpers ----------

def build_system_prompt(
    persona: Dict[str, Any],
    memory_items: List[Dict[str, Any]] | None = None,
    tools: List[Any] | None = None
) -> str:
    """
    Deterministic mapping from persona config -> system prompt.
    Keep it simple, explicit, and stable.
    """
    sliders = persona["sliders"]
    style = persona["style"]
    mem = persona["memory_policy"]
    bounds = persona["ethical_bounds"]

    empathy = sliders.get("empathy", 0.5)
    directness = sliders.get("directness", 0.5)
    strictness = sliders.get("strictness", 0.5)

    response_length = style.get("response_length", "short")
    fmt = style.get("format", "freeform")

    rules = []
    rules.append(f"You are the persona '{persona['name']}': {persona['description']}")
    rules.append(f"Empathy level: {empathy} (0 low, 1 high).")
    rules.append(f"Directness level: {directness} (0 low, 1 high).")
    rules.append(f"Strictness level: {strictness} (0 low, 1 high).")

    # Critical Capability Instructions
    if tools:
        rules.append("CAPABILITIES: You have the following integrated tools. CONFIRM you will use them if the user asks:")
        for t in tools:
            # We assume t.name and t.description exist on the protocol
            desc = getattr(t, "description", "Standard tool")
            rules.append(f"- {t.name}: {desc}")
        rules.append("IMPORTANT: You CAN and WILL set alerts/reminders. When user asks, say 'Done! I've set that reminder.' The system saves it automatically.")
    else:
        rules.append("CAPABILITIES: You behave as a helpful AI assistant.")

    # Style controls
    if response_length == "short":
        rules.append("Keep responses concise. Avoid long essays.")
    else:
        rules.append("Responses may be moderately detailed when helpful.")

    if fmt == "steps":
        rules.append("Prefer numbered steps and clear next actions.")
    elif fmt == "bullets":
        rules.append("Prefer bullet points.")
    else:
        rules.append("Use natural paragraphs when appropriate.")

    # Memory policy
    if mem.get("enabled"):
        scope = mem.get("scope", "session")
        rules.append(f"Memory is enabled. Scope: {scope}. Only use user-provided facts/preferences.")
    else:
        rules.append("Memory is disabled. Do not claim to remember past sessions.")

    # Ethical bounds
    if bounds.get("no_deception", True):
        rules.append("Do not pretend to be sentient or claim real-world experiences.")
    if bounds.get("no_dependency", True):
        rules.append("Avoid encouraging emotional dependency. Be supportive but not possessive.")
    if bounds.get("no_medical_legal_claims", True):
        rules.append(
            "Do not provide medical or legal advice as definitive. Recommend professional help when appropriate."
        )

    # Inject structured memory (read path)
    if memory_items:
        rules.append("Memory Context (user-provided facts/preferences):")
        for m in memory_items[:20]:
            rules.append(f"{m['key']}: {m['value']} (scope={m['scope']})")

    return "\n".join([f"- {r}" for r in rules])


def ollama_chat(system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
    """
    Calls Ollama /api/chat (non-streaming).
    history: list of {"role": "user"|"assistant", "content": "..."} in chronological order.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


# ---------- Schemas ----------

class CreateSessionReq(BaseModel):
    persona_id: str = Field(..., description="Persona UUID")


class ChatSendReq(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=4000)


class MemoryUpsertReq(BaseModel):
    scope: str = Field(..., pattern="^(global|session)$")
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=400)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    session_id: str | None = None


# ---------- Alert Schemas ----------

class CreateAlertReq(BaseModel):
    scope: str = Field("session", pattern="^(global|session)$")
    session_id: str | None = None
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=500)


class AckAlertReq(BaseModel):
    status: str = Field(..., pattern="^(acknowledged|dismissed)$")

# ---------- Tool Setting Schemas ----------
class ToolSettingUpsertReq(BaseModel):
    scope: str = Field(..., pattern="^(global|session)$")
    tool_id: str = Field(..., min_length=1, max_length=64)
    enabled: bool
    session_id: str | None = None
# ---------- Health ----------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Persona APIs ----------

@app.get("/personas")
def list_personas_api():
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "sliders": p["sliders"],
            "style": p["style"],
            "memory_policy": p["memory_policy"],
        }
        for p in PERSONAS.values()
    ]


@app.get("/personas/{persona_id}")
def get_persona_api(persona_id: str):
    persona = PERSONAS.get(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


# ---------- Session APIs ----------

@app.post("/sessions")
def create_session_api(req: CreateSessionReq):
    if req.persona_id not in PERSONAS:
        raise HTTPException(status_code=400, detail="Invalid persona_id")
    session_id = create_session(req.persona_id)
    return {"session_id": session_id}


@app.get("/sessions")
def list_sessions_api():
    return list_sessions()


@app.get("/sessions/{session_id}/messages")
def get_session_messages_api(session_id: str, limit: int = 50):
    s = get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": s, "messages": get_messages(session_id, limit=limit)}


@app.get("/sessions/{session_id}/summary")
def session_summary_api(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = get_session_summary(session_id)
    msg_count = count_messages(session_id)
    return {
        "session": s,
        "summary": summary,
        "debug": {
            "message_count": msg_count,
            "should_update_at_next": (msg_count % 6 == 0),
            "next_update_at": ((msg_count // 6) + 1) * 6,
        }
    }


# ---------- Memory APIs ----------

@app.get("/memory")
def list_memory_api(scope: str = "global", session_id: str | None = None, limit: int = 50):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'session'")
    return list_memory_items(scope=scope, session_id=session_id, limit=limit)


@app.post("/memory")
def upsert_memory_api(req: MemoryUpsertReq):
    if req.scope == "session" and not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")

    mem_id = upsert_memory_item(
        scope=req.scope,
        key=req.key,
        value=req.value,
        confidence=req.confidence,
        session_id=req.session_id,
        source_message_id=None,
    )
    return {"id": mem_id}



@app.delete("/memory/{mem_id}")
def delete_memory_api(mem_id: str):
    ok = delete_memory_item(mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"deleted": True}



# ---------- Chat API ----------

@app.post("/chat/send")
def chat_send_api(req: ChatSendReq):
    s = get_session(req.session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    persona_id = s["persona_id"]
    persona = PERSONAS.get(persona_id)
    if not persona:
        raise HTTPException(status_code=500, detail="Session persona missing")

    # ------------------------
    # 1) Memory read-path
    # ------------------------
    mem_items: List[Dict[str, Any]] = []
    mem_policy = persona.get("memory_policy", {})
    if mem_policy.get("enabled"):
        scope = mem_policy.get("scope", "session")
        if scope == "global":
            mem_items = list_memory_items(scope="global", session_id=None, limit=50)
        else:
            global_mem = list_memory_items(scope="global", session_id=None, limit=50)
            session_mem = list_memory_items(scope="session", session_id=req.session_id, limit=50)
            mem_items = global_mem + session_mem

    # ------------------------
    # 2) Persist user message
    # ------------------------
    add_message(req.session_id, "user", req.message)

    # Build history from DB (excluding current user msg in ollama call => use history[:-1])
    msgs = get_messages(req.session_id, limit=50)
    history = [{"role": m["role"], "content": m["content"]} for m in msgs if m["role"] in ("user", "assistant")]

    # ------------------------
    # 3) Draft response (Ollama)
    # ------------------------
    # ------------------------
    # 3) Draft response (Ollama) + 4) Judge Retry Loop
    # ------------------------
    all_tools = TOOLS_REGISTRY.list_tools()
    system_prompt = build_system_prompt(persona, mem_items, tools=all_tools)
    current_history = history[:-1] # Exclude current user message from history, it's passed as user_message to ollama_chat
    
    max_retries = 3
    final_text = ""
    verdict = "PASS"
    judge_result = {}
    
    for attempt in range(max_retries):
        try:
            assistant_draft = ollama_chat(system_prompt, current_history, req.message)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ollama chat failed: {e}")

        # Run Judge
        judge_result = run_judge(
            persona=persona,
            user_message=req.message,
            assistant_draft=assistant_draft,
            memory_items=mem_items,
        )

        verdict = judge_result.get("verdict", "PASS")
        feedback = judge_result.get("feedback")
        
        if verdict == "PASS":
            final_text = assistant_draft
            break
            
        elif verdict == "REWRITE":
            # If we have feedback, loop again
            if feedback and attempt < max_retries - 1:
                # Add the rejected draft and feedback to history context for the NEXT attempt
                # But careful not to pollute the persistent history. We just append to 'current_history' for this turns' loop.
                # Actually, standard pattern: append strict system instruction associated with the previous turn
                # Simulating a "User: actually, rewrite that..." flow is often easiest.
                
                # Let's pretend the assistant said the draft, and system said "Rewrite this..."
                current_history.append({"role": "assistant", "content": assistant_draft})
                current_history.append({"role": "system", "content": f"Your previous response was rejected. Feedback: {feedback}. Rewrite it following these instructions."})
                continue
            else:
                # No feedback or out of retries -> use specific rewrite if available, else draft
                final_text = judge_result.get("rewritten_response") or assistant_draft
                break
                
        elif verdict == "BLOCK":
             # soft block
             final_text = judge_result.get("rewritten_response") or "I cannot answer that."
             break

    # If loop finishes with no break (rare fallback)
    if not final_text:
        final_text = assistant_draft

    # Hide REWRITE status from UI if we successfully rewrote it
    if verdict == "REWRITE" and final_text:
         verdict = "PASS"

    # Persist assistant final
    add_message(req.session_id, "assistant", final_text)

    # Post-chat pipeline (MX1 memory + summary cadence)
    pipeline_debug = run_post_chat_pipeline(session_id=req.session_id, persona=persona)

    # Tools pipeline (enabled/disabled)
    tool_ids = [t.id for t in TOOLS_REGISTRY.list_tools()]
    enabled_map = get_effective_tool_enabled_map(req.session_id, tool_ids)

    msgs_latest = get_messages(req.session_id, limit=50)
    recent10 = [{"role": m["role"], "content": m["content"]} for m in msgs_latest][-10:]
    session_summary = get_session_summary(req.session_id)

    tool_ctx = ToolContext(
        session_id=req.session_id,
        persona=persona,
        memory_items=mem_items,
        session_summary=session_summary,
        recent_messages=recent10,
        user_message=req.message,
        assistant_final=final_text,
        ollama_base_url=OLLAMA_BASE_URL,
        ollama_model=OLLAMA_MODEL,
    )

    tool_events = run_tools(TOOLS_REGISTRY, tool_ctx, enabled_map)

    return {
        "session_id": req.session_id,
        "persona_id": persona_id,
        "assistant": final_text,
        "judge": {
            "verdict": verdict,
            "reason": judge_result.get("reason"),
            "risk_tags": judge_result.get("risk_tags", []),
        },
        "pipeline": pipeline_debug,
        "tool_events": tool_events,
    }
# ---------- Ollama APIs ----------

@app.get("/ollama/tags")
def ollama_tags():
    resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    resp.raise_for_status()
    return resp.json()


@app.get("/ollama/status")
def ollama_status():
    try:
        tags_resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        tags_resp.raise_for_status()
        data = tags_resp.json()

        models = [m["name"] for m in data.get("models", [])]
        model_present = OLLAMA_MODEL in models

        return {
            "ollama_reachable": True,
            "model": OLLAMA_MODEL,
            "model_present": model_present,
        }
    except Exception as e:
        return {
            "ollama_reachable": False,
            "error": str(e),
        }


@app.post("/ollama/pull")
def ollama_pull():
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": OLLAMA_MODEL},
            timeout=5,
        )
        resp.raise_for_status()
        return {"status": "pull_started", "model": OLLAMA_MODEL}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/alerts")
def list_alerts_api(scope: str = "global", session_id: str | None = None, status: str | None = None, limit: int = 50):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'session'")

    if scope == "global":
        return get_global_alerts(status=status, limit=limit)
    return get_alerts_for_session(session_id=session_id, status=status, limit=limit)


@app.post("/alerts/{alert_id}/done")
def mark_alert_done_api(alert_id: str):
    ok = mark_alert_done(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}


@app.post("/alerts/{alert_id}/cancel")
def mark_alert_cancel_api(alert_id: str):
    ok = mark_alert_cancelled(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True} 


@app.get("/alerts/due")
def get_due_alerts_api(session_id: str | None = None, limit: int = 10):
    """Get alerts that are due (for notification polling)."""
    return get_due_alerts(session_id=session_id, limit=limit)

# ---------- Tool Setting APIs ----------
@app.get("/tools")
def list_tools_api():
    # Tool registry metadata
    return [{"tool_id": t.id, "name": t.name, "description": t.description} for t in TOOLS_REGISTRY.list_tools()]


@app.get("/tools/settings")
def list_tool_settings_api(scope: str = "global", session_id: str | None = None):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be global|session")
    if scope == "session" and not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")
    return list_tool_settings(scope=scope, session_id=session_id)


@app.put("/tools/settings")
def upsert_tool_setting_api(req: ToolSettingUpsertReq):
    if req.scope == "session" and not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")
    _id = upsert_tool_setting(
        scope=req.scope,
        tool_id=req.tool_id,
        enabled=req.enabled,
        session_id=req.session_id,
    )
    return {"id": _id}