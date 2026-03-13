import os
import json
import uuid
import shlex
import shutil
import logging
import operator
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Annotated
from typing_extensions import TypedDict

import chromadb
import pdfplumber
from openai import OpenAI
from tavily import TavilyClient
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from duckduckgo_search import DDGS
from dotenv import load_dotenv
import motor.motor_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Resume RAG API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SCHEMA_FILE = DATA_DIR / "schema.json"
EXTRACTED_FILE = DATA_DIR / "extracted_data.json"
CHROMA_DIR = DATA_DIR / "chroma_db"

for d in [DATA_DIR, UPLOADS_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_SCHEMA = {
    "name": "Full name of the candidate",
    "email": "Email address",
    "phone": "Phone number",
    "location": "City and/or Country",
    "summary": "Professional summary or objective statement",
    "education": "Degrees with institution name and graduation year (all degrees)",
    "experience": "All work experiences with company name, job title, duration/dates, and key responsibilities",
    "skills": "Technical skills, programming languages, tools and frameworks",
    "certifications": "Professional certifications or licenses",
    "languages": "Languages spoken and proficiency level",
    "total_experience_years": "Total years of professional experience (number only)",
}

if not SCHEMA_FILE.exists():
    SCHEMA_FILE.write_text(json.dumps(DEFAULT_SCHEMA, indent=2))
if not EXTRACTED_FILE.exists():
    EXTRACTED_FILE.write_text(json.dumps([], indent=2))

# ─── MongoDB ─────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://resumeiq_mongo:27017")
try:
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = mongo_client.resumeiq
    chat_collection = db.chat_sessions
    chat_events_collection = db.chat_events
    resumes_store_collection = db.resumes
    app_state_collection = db.app_state
    logger.info("Connected to MongoDB.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    mongo_client = None
    db = None
    chat_collection = None
    chat_events_collection = None
    resumes_store_collection = None
    app_state_collection = None

# ─── ChromaDB ────────────────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
resume_collection = chroma_client.get_or_create_collection(name="resume_chunks")

# ─── MCP ─────────────────────────────────────────────────────────────────────
MCP_SERVER_COMMAND = os.getenv("MCP_SERVER_COMMAND", "python mcp_local_server.py")


def _mcp_params() -> StdioServerParameters:
    parts = shlex.split(MCP_SERVER_COMMAND)
    if not parts:
        raise ValueError("MCP_SERVER_COMMAND is empty")
    return StdioServerParameters(command=parts[0], args=parts[1:], env=dict(os.environ))


async def mcp_list_tools() -> list[dict]:
    """Fetch callable MCP tools from a real MCP stdio server."""
    try:
        params = _mcp_params()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                tools = getattr(listing, "tools", [])
                normalized = []
                for t in tools:
                    normalized.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": getattr(t, "description", "") or "MCP tool",
                                "parameters": getattr(t, "inputSchema", None)
                                or getattr(t, "input_schema", None)
                                or {"type": "object", "properties": {}},
                            },
                        }
                    )
                return normalized
    except Exception as e:
        logger.warning(f"MCP list_tools unavailable: {e}")
        return []


async def mcp_call_tool(name: str, args: dict) -> str:
    """Execute a tool against MCP server."""
    try:
        params = _mcp_params()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, args or {})
                content = getattr(result, "content", []) or []
                if not content:
                    return str(result)
                parts = []
                for c in content:
                    txt = getattr(c, "text", None)
                    if txt:
                        parts.append(txt)
                    else:
                        parts.append(str(c))
                return "\n".join(parts)
    except Exception as e:
        return f"MCP tool error ({name}): {e}"


# ─── Storage helpers (Mongo-first, file mirror for backward compatibility) ──
def _read_extracted_file() -> list:
    try:
        return json.loads(EXTRACTED_FILE.read_text())
    except Exception:
        return []


def _write_extracted_file(data: list):
    EXTRACTED_FILE.write_text(json.dumps(data, indent=2))


async def get_schema_data() -> dict:
    if app_state_collection is not None:
        doc = await app_state_collection.find_one({"key": "schema"}, {"_id": 0, "schema": 1})
        if doc and isinstance(doc.get("schema"), dict) and doc["schema"]:
            return doc["schema"]
    return json.loads(SCHEMA_FILE.read_text())


async def set_schema_data(schema: dict):
    SCHEMA_FILE.write_text(json.dumps(schema, indent=2))
    if app_state_collection is not None:
        await app_state_collection.update_one(
            {"key": "schema"},
            {
                "$set": {
                    "key": "schema",
                    "schema": schema,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
            upsert=True,
        )


async def load_extracted() -> list:
    if resumes_store_collection is not None:
        docs = []
        cursor = resumes_store_collection.find({}, {"_id": 0}).sort("uploaded_at", -1)
        async for d in cursor:
            docs.append(d)
        if docs:
            return docs
    return _read_extracted_file()


async def upsert_extracted_entry(entry: dict):
    # Always mirror legacy file for compatibility with existing workflows/tools.
    data = _read_extracted_file()
    idx = next((i for i, x in enumerate(data) if x.get("id") == entry["id"]), None)
    if idx is None:
        data.append(entry)
    else:
        data[idx] = entry
    _write_extracted_file(data)

    if resumes_store_collection is not None:
        await resumes_store_collection.update_one({"id": entry["id"]}, {"$set": entry}, upsert=True)


async def delete_extracted_entry(resume_id: str):
    data = [e for e in _read_extracted_file() if e.get("id") != resume_id]
    _write_extracted_file(data)
    if resumes_store_collection is not None:
        await resumes_store_collection.delete_one({"id": resume_id})


@app.on_event("startup")
async def startup_sync():
    """Migrate file-based state to Mongo so Mongo stores full app data."""
    try:
        if app_state_collection is not None:
            await app_state_collection.create_index("key", unique=True)
            schema_doc = await app_state_collection.find_one({"key": "schema"})
            if schema_doc is None:
                await app_state_collection.insert_one(
                    {
                        "key": "schema",
                        "schema": json.loads(SCHEMA_FILE.read_text()),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )

        if resumes_store_collection is not None:
            await resumes_store_collection.create_index("id", unique=True)
            for entry in _read_extracted_file():
                if entry.get("id"):
                    await resumes_store_collection.update_one({"id": entry["id"]}, {"$set": entry}, upsert=True)

        if chat_collection is not None:
            await chat_collection.create_index("session_id", unique=True)
            await chat_collection.create_index("created_at")

        if chat_events_collection is not None:
            await chat_events_collection.create_index("session_id")
            await chat_events_collection.create_index("created_at")

        logger.info("Startup sync complete.")
    except Exception as e:
        logger.warning(f"Startup sync skipped/failed: {e}")


# ─── LLM + Search ─────────────────────────────────────────────────────────────
logger.info("Loading sentence transformer model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

llm = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.2,
)

openai_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

_tavily_key = os.getenv("TAVILY_API_KEY", "")
tavily_client = TavilyClient(api_key=_tavily_key) if _tavily_key else None
if tavily_client:
    logger.info("Tavily search client initialized.")
else:
    logger.warning("TAVILY_API_KEY not set — falling back to DuckDuckGo search.")


def web_search(query: str, max_results: int = 5) -> list[dict]:
    if tavily_client:
        try:
            resp = tavily_client.search(query=query, search_depth="basic", max_results=max_results)
            results = []
            for r in resp.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "href": r.get("url", ""),
                    "body": r.get("content", ""),
                })
            if results:
                return results
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}; trying DuckDuckGo fallback")

    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return []


def classify_intent(message: str, has_resumes: bool) -> str:
    if not has_resumes:
        return "web"

    try:
        resp = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=5,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify whether a user question is about resume/candidate data OR needs a live web search. "
                        "Reply with exactly one word: web or resume."
                    ),
                },
                {"role": "user", "content": message},
            ],
        )
        label = resp.choices[0].message.content.strip().lower()
        return "web" if label.startswith("web") else "resume"
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}; defaulting to web")
        return "web"


def generate_standalone_query(message: str, chat_history: list) -> str:
    if not chat_history:
        return message

    history_text = ""
    for msg in chat_history[-6:]:
        history_text += f"{msg.role.capitalize()}: {msg.text}\n"

    prompt = f"""Given the conversation history and latest user message, rewrite the latest message as a standalone query.

Conversation History:
{history_text}

Latest user message: {message}

Standalone query:"""

    try:
        response = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=64,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        resolved = response.choices[0].message.content.strip()
        if resolved.startswith('"') and resolved.endswith('"'):
            resolved = resolved[1:-1]
        return resolved
    except Exception as e:
        logger.warning(f"Failed to generate standalone query: {e}")
        return message


# ─── LangGraph State ──────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    intent: str
    resume_id: Optional[str]
    results: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    context: str
    standalone_query: str
    session_id: str
    answer: str
    tool_trace: List[Dict[str, Any]]


def intent_node(state: AgentState):
    query = state["standalone_query"]
    has_resumes = resume_collection.count() > 0
    intent = classify_intent(query, has_resumes)
    return {"intent": intent}


def retrieval_node(state: AgentState):
    if state["intent"] != "resume":
        return {"citations": []}

    query = state["standalone_query"]
    resume_id = state["resume_id"]
    query_vec = embedding_model.encode([query]).tolist()
    where_clause = {"resume_id": resume_id} if resume_id else None

    results = resume_collection.query(
        query_embeddings=query_vec,
        n_results=min(8, resume_collection.count() or 8),
        where=where_clause,
    )

    relevant_chunks = []
    citations = []
    if results and results.get("documents") and len(results["documents"][0]) > 0:
        for i, doc_text in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            chunk_id = results["ids"][0][i] if results.get("ids") else None
            citation_num = i + 1

            relevant_chunks.append(f"[{citation_num}] Source: {meta.get('original_filename', 'unknown')}\n{doc_text}")
            citations.append(
                {
                    "citation": citation_num,
                    "chunk_id": chunk_id,
                    "resume_id": meta.get("resume_id"),
                    "chunk_index": meta.get("chunk_index"),
                    "source": meta.get("original_filename"),
                    "text": doc_text,
                }
            )

    context = "\n\n---\n\n".join(relevant_chunks)
    return {
        "context": context,
        "results": [{"type": "rag", "count": len(relevant_chunks)}],
        "citations": citations,
    }


def web_search_node(state: AgentState):
    if state["intent"] != "web":
        return {"citations": []}

    query = state["standalone_query"]
    results = web_search(query)

    snippets = []
    sources = []
    citations = []
    for i, r in enumerate(results):
        if r.get("body"):
            n = i + 1
            snippets.append(f"[{n}] {r.get('title', '')}\nURL: {r.get('href', '')}\n{r.get('body', '')}")
            sources.append(f"{n}. [{r.get('title', 'Source')}]({r.get('href', '')})")
            citations.append(
                {
                    "citation": n,
                    "source": r.get("title", ""),
                    "url": r.get("href", ""),
                    "text": r.get("body", ""),
                    "type": "web",
                }
            )

    context = "\n\n".join(snippets)
    if sources:
        context += "\n\n---\n**Sources:**\n" + "\n".join(sources)

    return {"context": context, "results": results, "citations": citations}


async def generator_node(state: AgentState):
    intent = state["intent"]
    context = state["context"]
    query = state["standalone_query"]

    if intent == "resume":
        system_prompt = (
            "You are a precise HR assistant (ResumeIQ). "
            "Answer questions about candidates using ONLY provided resume context. "
            "You MUST cite source numbers like [1], [2]. Keep answers concise and factual."
        )
    else:
        system_prompt = (
            "You are a helpful assistant with web results context. "
            "Use ONLY provided search snippets. Cite [1], [2], etc."
        )

    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"][-6:],
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {query}"),
    ]

    tools = await mcp_list_tools()
    llm_runner = llm.bind_tools(tools) if tools else llm
    response = await llm_runner.ainvoke(messages)

    tool_trace = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls[:3]:
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("args", {})
            tool_result = await mcp_call_tool(tool_name, tool_args)
            tool_trace.append({"tool": tool_name, "args": tool_args, "result": tool_result[:4000]})

            messages.append(AIMessage(content="", tool_calls=[tool_call]))
            messages.append(HumanMessage(content=f"Tool result ({tool_name}):\n{tool_result}"))

        response = await llm.ainvoke(messages)

    return {"answer": response.content, "tool_trace": tool_trace}


workflow = StateGraph(AgentState)
workflow.add_node("intent_router", intent_node)
workflow.add_node("resume_retrieve", retrieval_node)
workflow.add_node("web_lookup", web_search_node)
workflow.add_node("answer_generate", generator_node)
workflow.set_entry_point("intent_router")


def route_intent(state: AgentState):
    return "resume_retrieve" if state["intent"] == "resume" else "web_lookup"


workflow.add_conditional_edges("intent_router", route_intent)
workflow.add_edge("resume_retrieve", "answer_generate")
workflow.add_edge("web_lookup", "answer_generate")
workflow.add_edge("answer_generate", END)
graph = workflow.compile()


# ─── Request Models ───────────────────────────────────────────────────────────
class SchemaUpdate(BaseModel):
    schema: dict


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    message: str
    resume_id: Optional[str] = None
    session_id: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/schema")
async def get_schema():
    return await get_schema_data()


@app.put("/api/schema")
async def update_schema(body: SchemaUpdate):
    if not isinstance(body.schema, dict) or not body.schema:
        raise HTTPException(status_code=400, detail="Schema must be a non-empty object.")
    await set_schema_data(body.schema)
    return {"success": True, "message": "Schema updated. Next uploads will use this schema."}


@app.get("/api/resumes")
async def list_resumes():
    extracted = await load_extracted()
    return [
        {
            "id": e["id"],
            "original_filename": e.get("original_filename", e.get("filename", "")),
            "filename": e.get("filename", ""),
            "uploaded_at": e.get("uploaded_at", ""),
        }
        for e in extracted
    ]


@app.get("/api/resume/{resume_id}/file")
async def serve_resume(resume_id: str):
    for e in await load_extracted():
        if e.get("id") == resume_id:
            path = UPLOADS_DIR / e.get("filename", "")
            if path.exists():
                return FileResponse(
                    str(path),
                    media_type="application/pdf",
                    filename=e.get("original_filename", e.get("filename", "")),
                )
    raise HTTPException(status_code=404, detail="Resume not found")


@app.delete("/api/resume/{resume_id}")
async def delete_resume(resume_id: str):
    extracted = await load_extracted()
    entry = next((e for e in extracted if e.get("id") == resume_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Resume not found")

    path = UPLOADS_DIR / entry.get("filename", "")
    if path.exists():
        path.unlink()

    await delete_extracted_entry(resume_id)

    try:
        resume_collection.delete(where={"resume_id": resume_id})
    except Exception as e:
        logger.warning(f"Failed to delete from ChromaDB: {e}")

    return {"success": True}


@app.post("/api/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    resume_id = str(uuid.uuid4())
    stored_filename = f"{resume_id}_{file.filename}"
    filepath = UPLOADS_DIR / stored_filename

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    raw_text = ""
    try:
        with pdfplumber.open(str(filepath)) as pdf:
            for page in pdf.pages:
                raw_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        filepath.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Failed to read PDF: {e}")

    if not raw_text.strip():
        filepath.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No readable text found in PDF.")

    schema = await get_schema_data()
    schema_str = json.dumps(schema, indent=2)

    prompt = f"""You are an expert resume parser. Extract the following fields from the resume text.
Return ONLY a valid JSON object. Do NOT include markdown fences, explanation or any other text.
If a field cannot be found, use null or an empty string.

Schema to extract (key = field name, value = description of what to extract):
{schema_str}

Resume text:
\"\"\"
{raw_text[:8000]}
\"\"\"

Return only the JSON object:"""

    try:
        response = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_response = response.choices[0].message.content.strip()

        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            raw_response = "\n".join(lines[1:-1] if lines and lines[-1] == "```" else lines[1:])

        extracted_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed (invalid JSON): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction API error: {e}")

    entry = {
        "id": resume_id,
        "filename": stored_filename,
        "original_filename": file.filename,
        "uploaded_at": datetime.utcnow().isoformat(),
        "data": extracted_data,
        "raw_text": raw_text,
    }
    await upsert_extracted_entry(entry)

    chunk_size = 500
    sub_chunks = [raw_text[i : i + chunk_size].strip() for i in range(0, len(raw_text), chunk_size)]
    sub_chunks = [c for c in sub_chunks if c]

    embeddings = embedding_model.encode(sub_chunks).tolist()
    ids = [f"{resume_id}_{i}" for i in range(len(sub_chunks))]
    metadatas = [
        {
            "resume_id": resume_id,
            "original_filename": file.filename,
            "chunk_index": i,
        }
        for i in range(len(sub_chunks))
    ]

    resume_collection.add(documents=sub_chunks, embeddings=embeddings, metadatas=metadatas, ids=ids)

    return {"success": True, "id": resume_id, "extracted": extracted_data}


@app.get("/api/extracted")
async def get_all_extracted():
    return await load_extracted()


@app.get("/api/chat/history")
async def get_chat_history():
    if chat_collection is None:
        return []

    sessions = []
    try:
        cursor = chat_collection.find({}, {"session_id": 1, "created_at": 1, "messages": 1}).sort("created_at", -1)
        async for doc in cursor:
            title = "New Chat"
            for m in doc.get("messages", []):
                if m.get("role") == "user":
                    t = m.get("text", "")
                    title = t[:30] + "..." if len(t) > 30 else t
                    break
            sessions.append(
                {
                    "session_id": doc.get("session_id"),
                    "title": title,
                    "created_at": doc.get("created_at"),
                }
            )
        return sessions
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return []


@app.get("/api/chat/history/{session_id}")
async def get_chat_session(session_id: str):
    if chat_collection is None:
        raise HTTPException(status_code=503, detail="Database not available")

    doc = await chat_collection.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return doc


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    chat_history_objs = []

    if chat_collection is not None:
        doc = await chat_collection.find_one({"session_id": session_id})
        if doc and "messages" in doc:
            chat_history_objs = [ChatMessage(**m) for m in doc["messages"] if "role" in m and "text" in m]

    standalone_query = req.message
    if chat_history_objs:
        standalone_query = generate_standalone_query(req.message, chat_history_objs)

    langchain_history = []
    for m in chat_history_objs:
        if m.role == "assistant":
            langchain_history.append(AIMessage(content=m.text))
        else:
            langchain_history.append(HumanMessage(content=m.text))

    initial_state: AgentState = {
        "messages": langchain_history + [HumanMessage(content=req.message)],
        "intent": "",
        "resume_id": req.resume_id,
        "results": [],
        "citations": [],
        "context": "",
        "standalone_query": standalone_query,
        "session_id": session_id,
        "answer": "",
        "tool_trace": [],
    }

    try:
        final_state = await graph.ainvoke(initial_state)
        answer = final_state["answer"]
        citations = final_state.get("citations", [])
        intent = final_state.get("intent", "")
        tool_trace = final_state.get("tool_trace", [])
    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    if chat_collection is not None:
        new_messages = [
            {"role": "user", "text": req.message, "standalone_query": standalone_query},
            {
                "role": "assistant",
                "text": answer,
                "intent": intent,
                "citations": citations,
                "tool_trace": tool_trace,
            },
        ]
        await chat_collection.update_one(
            {"session_id": session_id},
            {
                "$setOnInsert": {"created_at": datetime.utcnow().isoformat()},
                "$push": {"messages": {"$each": new_messages}},
            },
            upsert=True,
        )

    if chat_events_collection is not None:
        await chat_events_collection.insert_one(
            {
                "session_id": session_id,
                "resume_id": req.resume_id,
                "query": req.message,
                "standalone_query": standalone_query,
                "intent": intent,
                "answer": answer,
                "citations": citations,
                "tool_trace": tool_trace,
                "created_at": datetime.utcnow().isoformat(),
            }
        )

    # Keep both keys for backward compatibility with existing frontend/tests.
    return {
        "answer": answer,
        "response": answer,
        "session_id": session_id,
        "intent": intent,
        "citations": citations,
    }
