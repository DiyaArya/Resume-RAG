# ResumeIQ — Intelligent Resume Analysis & RAG Chatbot

ResumeIQ is a full-stack, AI-powered application designed to streamline the resume screening process. It extracts structured data from PDF resumes, stores them in a lightning-fast vector database, and provides a contextual chatbot that can answer complex questions about candidates.

## 🌟 Key Features
- **Intelligent Extraction:** Automatically extracts names, skills, experience, and contact info.
- **Advanced RAG Chatbot:** Query multiple candidates using semantic search powered by **ChromaDB**.
- **Source Citations:** AI responses include verbatim citations from the original resumes.
- **Persistent Memory:** Chat history is saved in **MongoDB**, allowing you to resume conversations.
- **Web Search Fallback:** If a question isn't about candidates, it searches the live web (Tavily/DuckDuckGo).
- **Dockerized:** Runs anywhere with a single command.

## 🚀 Tech Stack
| Component | Technology |
|---|---|
| **Language** | Python 3.11 |
| **API Framework** | FastAPI |
| **LLM** | Groq (`llama-3.3-70b-versatile`) |
| **Vector DB** | ChromaDB (Unified storage & metadata filtering) |
| **Database** | MongoDB (Persistent chat history) |
| **Frontend** | React 18 + Vite |
| **Search** | Tavily / DuckDuckGo |

---

## 🛠️ Prerequisites
- Docker & Docker Compose
- **Groq API Key** ([Get it here](https://console.groq.com))
- **Tavily API Key** (Optional, for better web search)

---

## 🏗️ Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/DiyaArya/Resume-RAG.git
cd Resume-RAG
```

### 2. Configure Environment
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

### 3. Start the application
```bash
docker compose up --build -d
```
*Wait ~5-10 minutes on first run for PyTorch and Model downloads.*

Access the app at: **http://localhost:3000**

---

## 📱 Using the App

### 1. Schema Editor (`/`)
Define what fields you want to extract. Any change here instantly updates the database schema for future uploads.

### 2. Resume Library (`/upload`)
Upload PDF resumes directly. They are processed, indexed, and stored automatically.

### 3. Insights & Chat (`/data`)
- **Table View:** See all extracted data in a spreadsheet format.
- **Chat Panel:** Talk to your resumes. Ask things like:
  - *"Who has the strongest background in Python?"*
  - *"Compare Peter and Sarah for a Senior Dev role."*
  - *"Summarize Hayden's leadership experience."*
- **History:** Toggle the History dropdown to switch between past chat sessions.

---

## 📂 Project Structure
```
├── backend/
│   ├── data/                 # Persistent storage (PDFs, ChromaDB)
│   ├── main.py               # FastAPI logic
│   └── Dockerfile
├── frontend/
│   ├── src/                  # React source
│   └── Dockerfile
└── docker-compose.yml        # Orchestration (Backend, Frontend, MongoDB)
```

## 📜 License
Provided as-is for educational and professional screening purposes.
