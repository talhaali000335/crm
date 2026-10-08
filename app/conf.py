import os
MODELS = [m.strip() for m in os.getenv("GROQ_MODELS", "llama-3.3-70b-versatile,llama-3.1-8b-instant").split(",")]
MODE_LIST = [("ask", "Ask CRM (RAG)"), ("summary", "Summarize account"), ("email", "Draft email"),
             ("next", "Next best actions"), ("general", "General chat (no RAG)")]
