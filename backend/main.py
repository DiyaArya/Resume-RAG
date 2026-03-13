import os
import json
import uuid
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Annotated, TypedDict
import operator

import chromadb
from chromadb.config import Settings
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

# LangGraph & LangChain imports
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Resume RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── DB Connection ────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://resumeiq_mongo:27017")
try:
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = mongo_client.resumeiq
    chat_collection = db.chat_sessions
    logger.info("Connected to MongoDB.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    chat_collection = None

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
UPLOADS_DIR   = DATA_DIR / "uploads"
SCHEMA_FILE   = DATA_DIR / "schema.json"
EXTRACTED_FILE = DATA_DIR / "extracted_data.json"
CHROMA_DIR    = DATA_DIR / "chroma_db"

# ─── ChromaDB Client ────────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
resume_collection = chroma_client.get_or_create_collection(name="resume_chunks")

# ─── MCP Tools ─────────────────────────────────────────────────────────────
# Pre-defined tools for the LLM. In a production app, these results would 
# come dynamically from connected MCP servers.
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_project_file",
            "description": "Read the content of a file in this project (ResumeIQ).",
            "parameters": {
                "type": "object",
                "properties": {
                    "rel_path": {
                        "type": "string",
                        "description": "Relative path to the file from project root (e.g., 'backend/main.py')"
                    }
                },
                "required": ["rel_path"]
            }
        }
    }
]

def execute_tool(name: str, args: dict) -> str:
    """Helper to execute local or MCP tools."""
    if name == "read_project_file":
        try:
            path = Path(BASE_DIR.parent) / args["rel_path"]
            if not path.is_file():
                return f"Error: File {args['rel_path']} not found."
            return path.read_text()
        except Exception as e:
            return f"Error reading file: {e}"
    return "Unknown tool."

# ─── LangGraph State & Config ────────────────────────────────────────────────
class AgentState(TypedDict):
    """The state of our resume assistant graph."""
    messages: Annotated[List[BaseMessage], operator.add]
    intent: str  # 'resume' | 'web'
    resume_id: Optional[str]
    results: List[Dict[str, Any]]
    context: str
    standalone_query: str
    session_id: str
    answer: str

# ─── LangChain / LLM Initialization ──────────────────────────────────────────
# Using ChatOpenAI with Groq base URL for LangChain compatibility
llm = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    temperature=0.2
)

# Create data directories (uploads, chroma, etc.)
for d in [DATA_DIR, UPLOADS_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Default schema ───────────────────────────────────────────────────────────
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
    "total_experience_years": "Total years of professional experience (number only)"
}

if not SCHEMA_FILE.exists():
    SCHEMA_FILE.write_text(json.dumps(DEFAULT_SCHEMA, indent=2))

if not EXTRACTED_FILE.exists():
    EXTRACTED_FILE.write_text(json.dumps([], indent=2))

# ─── ML models ────────────────────────────────────────────────────────────────
logger.info("Loading sentence transformer model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
DIMENSION = 384

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

# Note: FAISS to ChromaDB migration logic removed as migration is complete.

def load_extracted() -> list:
    return json.loads(EXTRACTED_FILE.read_text())

def save_extracted(data: list):
    EXTRACTED_FILE.write_text(json.dumps(data, indent=2))

# ─── Web search helper ───────────────────────────────────────────────────────
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Return search results using Tavily (primary) or DuckDuckGo (fallback)."""
    # — Try Tavily first (reliable, AI-native, not rate-limited) —
    if tavily_client:
        try:
            resp = tavily_client.search(
                query=query,
                search_depth="basic",
                max_results=max_results,
            )
            results = []
            for r in resp.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "href":  r.get("url", ""),
                    "body":  r.get("content", ""),
                })
            if results:
                logger.info(f"Tavily returned {len(results)} results for: {query[:60]}")
                return results
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}; trying DuckDuckGo fallback")

    # — Fallback: DuckDuckGo —
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        logger.info(f"DuckDuckGo returned {len(results)} results for: {query[:60]}")
        return results  # each item has 'title', 'href', 'body'
    except Exception as e:
        logger.warning(f"DuckDuckGo search also failed: {e}")
        return []

def classify_intent(message: str, has_resumes: bool) -> str:
    """Ask the LLM whether this message needs resume data or a web search.
    Returns 'resume' or 'web'.
    """
    if not has_resumes:
        return "web"  # no resumes loaded — always search the web

    try:
        resp = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=5,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify whether a user question is about resume/candidate data OR needs a live web search.\n"
                        "\n"
                        "Answer 'web' if the question involves ANY of these:\n"
                        "- Current prices (gold, stocks, crypto, oil, forex)\n"
                        "- Today's news, recent events, breaking news\n"
                        "- Live sports scores or standings\n"
                        "- Current weather\n"
                        "- Anything that changes day to day and requires up-to-date information\n"
                        "- General knowledge questions not related to any candidate or resume\n"
                        "\n"
                        "Answer 'resume' ONLY if the question is clearly about a specific candidate, "
                        "their skills, experience, education, or comparing multiple candidates.\n"
                        "\n"
                        "Reply with exactly one word: 'web' or 'resume'. Nothing else."
                    ),
                },
                {"role": "user", "content": message},
            ],
        )
        label = resp.choices[0].message.content.strip().lower()
        # Check for 'web' first to avoid false 'resume' matches
        return "web" if label.startswith("web") else "resume"
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}; defaulting to 'web'")
        return "web"

def generate_standalone_query(message: str, chat_history: list) -> str:
    """Uses the LLM to rewrite the user's message into a standalone query 
    given the chat history, resolving references like 'it' or 'they'."""
    if not chat_history:
        return message
        
    history_text = ""
    # Last 6 messages for context
    for msg in chat_history[-6:]:
        history_text += f"{msg.role.capitalize()}: {msg.text}\n"
        
    prompt = f"""Given the following conversation history and the user's latest message, rewrite the user's message to be a standalone query that can be understood without the context of the conversation. Keep it concise.
    
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
        # Clean up quotes if the model wrapped output
        if resolved.startswith('"') and resolved.endswith('"'):
            resolved = resolved[1:-1]
        return resolved
    except Exception as e:
        logger.warning(f"Failed to generate standalone query: {e}")
        return message

# ─── LangGraph Nodes ───────────────────────────────────────────────────────────

def intent_node(state: AgentState):
    """Classifies the user intent into 'resume' or 'web'."""
    logger.info("Node: intent_node")
    query = state["standalone_query"]
    has_resumes = resume_collection.count() > 0
    
    intent = classify_intent(query, has_resumes)
    return {"intent": intent}

def retrieval_node(state: AgentState):
    """Retrieves relevant resume chunks from ChromaDB."""
    logger.info("Node: retrieval_node")
    if state["intent"] != "resume":
        return {}
        
    query = state["standalone_query"]
    resume_id = state["resume_id"]
    
    # Semantic search
    query_vec = embedding_model.encode([query]).tolist()
    where_clause = {"resume_id": resume_id} if resume_id else None
    
    results = resume_collection.query(
        query_embeddings=query_vec,
        n_results=min(8, resume_collection.count() or 8),
        where=where_clause
    )
    
    relevant_chunks = []
    if results and results["documents"] and len(results["documents"][0]) > 0:
        for i in range(len(results["documents"][0])):
            doc_text = results["documents"][0][i]
            meta = results["metadatas"][0][i]
            citation_num = i + 1
            relevant_chunks.append(f"[{citation_num}] Source: {meta['original_filename']}\n{doc_text}")
            
    context = "\n\n---\n\n".join(relevant_chunks)
    return {"context": context, "results": [{"type": "rag", "count": len(relevant_chunks)}]}

def web_search_node(state: AgentState):
    """Performs a web search if the intent is 'web'."""
    logger.info("Node: web_search_node")
    if state["intent"] != "web":
        return {}
        
    query = state["standalone_query"]
    results = web_search(query)
    
    snippets = []
    sources = []
    for i, r in enumerate(results):
        if r.get("body"):
            snippets.append(f"[{i+1}] {r['title']}\nURL: {r['href']}\n{r['body']}")
            sources.append(f"{i+1}. [{r['title']}]({r['href']})")
            
    context = "\n\n".join(snippets)
    if sources:
        context += "\n\n---\n**Sources:**\n" + "\n".join(sources)
        
    return {"context": context, "results": results}

def generator_node(state: AgentState):
    """Generates the final answer using the collected context."""
    logger.info("Node: generator_node")
    intent = state["intent"]
    context = state["context"]
    query = state["standalone_query"]
    
    if intent == "resume":
        system_prompt = (
            "You are a precise HR assistant (ResumeIQ). "
            "Answer questions about candidates using the provided resume data. "
            "You MUST cite the source number using brackets like [1], [2], etc. "
            "If Comparing multiple candidates, name them clearly. Be concise and factual."
        )
    else:
        system_prompt = (
            "You are a helpful assistant with access to live web search results. "
            "Use ONLY the search results provided to answer. Cite sources by their number [1], [2], etc. "
            "If no results were found, rely on your knowledge but mention you didn't find specific live news."
        )
        
    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"][-6:], 
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {query}")
    ]
    
    # Bind tools to the LLM so it knows it can use them
    llm_with_tools = llm.bind_tools(AVAILABLE_TOOLS)
    response = llm_with_tools.invoke(messages)
    
    # Handle optional tool calls (one-pass pass-through for presentation)
    # Note: For full agentic loops, we'd use a tool-aware executor node.
    # For this presentation, we'll demonstrate a single tool-call pass.
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            logger.info(f"Agent using tool: {tool_name}")
            tool_result = execute_tool(tool_name, tool_args)
            
            # Re-run LLM with tool output
            messages.append(AIMessage(content="", tool_calls=[tool_call]))
            messages.append(HumanMessage(content=f"Tool result: {tool_result}"))
            response = llm.invoke(messages)

    return {"answer": response.content}

# ─── Graph Construction ─────────────────────────────────────────────────────

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("intent", intent_node)
workflow.add_node("retrieve", retrieval_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("generate", generator_node)

# Set Entry Point
workflow.set_entry_point("intent")

# Add Conditional Edges
def route_intent(state: AgentState):
    return "retrieve" if state["intent"] == "resume" else "web_search"

workflow.add_conditional_edges("intent", route_intent)

# Connect everything to generation
workflow.add_edge("retrieve", "generate")
workflow.add_edge("web_search", "generate")
workflow.add_edge("generate", END)

# Compile
graph = workflow.compile()

# ─── Request models ───────────────────────────────────────────────────────────
class SchemaUpdate(BaseModel):
    schema: dict

class ChatMessage(BaseModel):
    role: str
    text: str

class ChatRequest(BaseModel):
    message: str
    resume_id: Optional[str] = None  # None = query all resumes
    session_id: Optional[str] = None

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Schema ──
@app.get("/api/schema")
def get_schema():
    return json.loads(SCHEMA_FILE.read_text())

@app.put("/api/schema")
def update_schema(body: SchemaUpdate):
    if not isinstance(body.schema, dict) or not body.schema:
        raise HTTPException(status_code=400, detail="Schema must be a non-empty object.")
    SCHEMA_FILE.write_text(json.dumps(body.schema, indent=2))
    logger.info("Schema updated.")
    return {"success": True, "message": "Schema updated. Next uploads will use this schema."}


# ── Resumes ──
@app.get("/api/resumes")
def list_resumes():
    extracted = load_extracted()
    return [
        {
            "id": e["id"],
            "original_filename": e.get("original_filename", e["filename"]),
            "filename": e["filename"],
            "uploaded_at": e.get("uploaded_at", ""),
        }
        for e in extracted
    ]

@app.get("/api/resume/{resume_id}/file")
def serve_resume(resume_id: str):
    for e in load_extracted():
        if e["id"] == resume_id:
            path = UPLOADS_DIR / e["filename"]
            if path.exists():
                return FileResponse(
                    str(path),
                    media_type="application/pdf",
                    filename=e.get("original_filename", e["filename"]),
                )
    raise HTTPException(status_code=404, detail="Resume not found")

@app.delete("/api/resume/{resume_id}")
def delete_resume(resume_id: str):
    extracted = load_extracted()
    entry = next((e for e in extracted if e["id"] == resume_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Remove file
    path = UPLOADS_DIR / entry["filename"]
    if path.exists():
        path.unlink()

    # Remove from extracted store
    extracted = [e for e in extracted if e["id"] != resume_id]
    save_extracted(extracted)

    # Delete from ChromaDB
    try:
        resume_collection.delete(where={"resume_id": resume_id})
        logger.info(f"Deleted chunks for resume {resume_id} from ChromaDB")
    except Exception as e:
        logger.warning(f"Failed to delete from ChromaDB: {e}")

    return {"success": True}


# ── Upload & Extract ──
@app.post("/api/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    resume_id = str(uuid.uuid4())
    stored_filename = f"{resume_id}_{file.filename}"
    filepath = UPLOADS_DIR / stored_filename

    # Save file to disk
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    logger.info(f"Saved resume: {stored_filename}")

    # Extract raw text
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

    # Load current schema
    schema = json.loads(SCHEMA_FILE.read_text())
    schema_str = json.dumps(schema, indent=2)

    # Ask Claude to extract structured data
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

        # Strip markdown code fences if present
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            raw_response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        extracted_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {raw_response}")
        raise HTTPException(status_code=500, detail=f"Extraction failed (invalid JSON): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {e}")

    # Persist extracted data
    all_extracted = load_extracted()
    entry = {
        "id": resume_id,
        "filename": stored_filename,
        "original_filename": file.filename,
        "uploaded_at": datetime.now().isoformat(),
        "data": extracted_data,
    }
    all_extracted.append(entry)
    save_extracted(all_extracted)

    # Index in ChromaDB ─ chunk text into ~500-char pieces
    chunk_size = 500
    sub_chunks = [raw_text[i : i + chunk_size].strip() for i in range(0, len(raw_text), chunk_size)]
    sub_chunks = [c for c in sub_chunks if c]

    embeddings = embedding_model.encode(sub_chunks).tolist()
    ids = [f"{resume_id}_{i}" for i in range(len(sub_chunks))]
    metadatas = [
        {"resume_id": resume_id, "original_filename": file.filename, "chunk_index": i}
        for i in range(len(sub_chunks))
    ]

    resume_collection.add(
        documents=sub_chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )
    logger.info(f"Indexed {len(sub_chunks)} chunks for resume {resume_id} in ChromaDB")

    return {"success": True, "id": resume_id, "extracted": extracted_data}


# ── Extracted data ──
@app.get("/api/extracted")
def get_all_extracted():
    return load_extracted()


# ── Chat (RAG + Web Search) ──
@app.get("/api/chat/history")
async def get_chat_history():
    """Returns a list of all chat sessions, ordered by most recent."""
    if chat_collection is None:
        return []
    
    sessions = []
    try:
        cursor = chat_collection.find({}, {"session_id": 1, "created_at": 1, "messages": 1}).sort("created_at", -1)
        async for doc in cursor:
            # Generate a title from the first user message
            title = "New Chat"
            if "messages" in doc and len(doc["messages"]) > 0:
                for m in doc["messages"]:
                    if m.get("role") == "user":
                        text = m.get("text", "")
                        title = text[:30] + "..." if len(text) > 30 else text
                        break
            
            sessions.append({
                "session_id": doc.get("session_id"),
                "title": title,
                "created_at": doc.get("created_at")
            })
        return sessions
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return []

@app.get("/api/chat/history/{session_id}")
async def get_chat_session(session_id: str):
    """Returns the full message history for a given session."""
    if chat_collection is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    doc = await chat_collection.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
        
    return doc

@app.post("/api/chat")
async def chat(req: ChatRequest):
    # ── Database Session Init ────────────────────────────────────────────────
    session_id = req.session_id or str(uuid.uuid4())
    chat_history_objs = []
    
    if chat_collection is not None:
        doc = await chat_collection.find_one({"session_id": session_id})
        if doc and "messages" in doc:
            chat_history_objs = [ChatMessage(**m) for m in doc["messages"]]

    # ── Step 0: Resolve standalone query ─────────────────────────────────────
    standalone_query = req.message
    if chat_history_objs:
        standalone_query = generate_standalone_query(req.message, chat_history_objs)
        logger.info(f"Resolved query: '{standalone_query}'")

    # ── Step 1: Initialize Graph State ───────────────────────────────────────
    # Convert ChatMessage objects to LangChain BaseMessages
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
        "context": "",
        "standalone_query": standalone_query,
        "session_id": session_id,
        "answer": ""
    }

    # ── Step 2: Run Graph ────────────────────────────────────────────────────
    try:
        final_state = await graph.ainvoke(initial_state)
        answer = final_state["answer"]
    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # ── Step 3: Persist to DB ──────────────────────────────────────────────
    if chat_collection is not None:
        new_messages = [
            {"role": "user", "text": req.message},
            {"role": "assistant", "text": answer}
        ]
        await chat_collection.update_one(
            {"session_id": session_id},
            {
                "$setOnInsert": {"created_at": datetime.utcnow().isoformat()},
                "$push": {"messages": {"$each": new_messages}}
            },
            upsert=True
        )

    return {
        "answer": answer,
        "session_id": session_id
    }
