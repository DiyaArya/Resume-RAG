import urllib.request
import json

BASE = "http://localhost:8000"

print("=== Testing RAG Citations ===")
req = urllib.request.Request(
    f"{BASE}/api/chat",
    data=json.dumps({"message": "What are the core skills of Kamya Mehra?"}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
try:
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    print("\n--- Response ---")
    print(resp.get("response", ""))
    print("\n----------------")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, "read"): print(e.read().decode())
