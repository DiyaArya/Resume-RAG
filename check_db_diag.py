import motor.motor_asyncio
import asyncio
import os
import json

async def check_db():
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    db = client.resumeiq
    collection = db.chat_sessions
    
    count = await collection.count_documents({})
    print(f"Total sessions: {count}")
    
    cursor = collection.find({})
    async for doc in cursor:
        messages = doc.get("messages", [])
        has_created_at = "created_at" in doc
        print(f"Session: {doc.get('session_id')} | CreatedAt: {has_created_at} | Messages: {len(messages)}")
        if len(messages) > 0:
            print(f"  First msg: {messages[0].get('text')[:40]}...")

if __name__ == "__main__":
    asyncio.run(check_db())
