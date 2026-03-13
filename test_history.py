import urllib.request
import json

BASE = "http://localhost:8000"

# Step 1: Start a new chat and save the session_id
print("=== Step 1: Creating new chat session ===")
req = urllib.request.Request(
    f"{BASE}/api/chat",
    data=json.dumps({"message": "US Iran war updates"}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
try:
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    session_id = resp.get("session_id")
    print(f"session_id: {session_id}")
    print(f"response[:100]: {resp.get('response', '')[:100]}...")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, "read"): print(e.read().decode())
    exit(1)

# Step 2: Continue the same chat (contextual follow-up)
print("\n=== Step 2: Contextual follow-up in same session ===")
req2 = urllib.request.Request(
    f"{BASE}/api/chat",
    data=json.dumps({"message": "how will it affect India?", "session_id": session_id}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
try:
    resp2 = json.loads(urllib.request.urlopen(req2, timeout=60).read().decode())
    print(f"session_id (same?): {resp2.get('session_id') == session_id}")
    print(f"response[:200]: {resp2.get('response', '')[:200]}...")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, "read"): print(e.read().decode())

# Step 3: List all sessions from history 
print("\n=== Step 3: GET /api/chat/history ===")
try:
    history_resp = json.loads(urllib.request.urlopen(f"{BASE}/api/chat/history", timeout=10).read().decode())
    print(f"Total sessions: {len(history_resp)}")
    for s in history_resp[:3]:
        print(f"  - {s['session_id'][:8]}... | title: {s['title']}")
except Exception as e:
    print(f"Error: {e}")

# Step 4: Fetch that specific session's history
print(f"\n=== Step 4: GET /api/chat/history/{session_id[:8]}... ===")
try:
    session_resp = json.loads(urllib.request.urlopen(f"{BASE}/api/chat/history/{session_id}", timeout=10).read().decode())
    messages = session_resp.get("messages", [])
    print(f"Total messages in session: {len(messages)}")
    for m in messages:
        print(f"  [{m['role']}]: {m['text'][:80]}...")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, "read"): print(e.read().decode())
