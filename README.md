# Mini CRM (Django + LangGraph + Groq + ElevenLabs, Docker, AWS)
Screens: 1) Contacts CRUD  2) AI Assistant (memory + guardrails)  3) AI call scripts + voice.

## AI pipeline (LangGraph)
input_guard -> memory (per-thread) -> retrieve -> rerank -> generate (Groq, "reader") -> hallucination check -> retry once | safe fallback -> save
- **Retrieval rank:** BM25 and TF-IDF cosine, fused with Reciprocal Rank Fusion (RRF). Corpus = contacts, call logs, uploaded knowledge docs.
- **Re-rank:** Groq LLM scores each (query, passage) 0-10; falls back to RRF order on error.
- **Guardrails:** prompt-injection filter, email/phone rule check, LLM fact-checker; one stricter retry, then safe fallback.
- **Workspace options:** multiple chat threads, 5 modes, model picker, contact scope, Top-K, re-rank and guard toggles, source table showing BM25/TF-IDF/RRF/rerank per source.
- **Login:** first user is created on boot (ADMIN_USERNAME / ADMIN_PASSWORD; if unset a random password is printed: `docker compose logs web | grep ADMIN`).
- **Tests:** `docker compose run --rm web python manage.py test`

## Deploy on AWS (free tier) via GitHub
1. Launch EC2 (Amazon Linux 2023, t2/t3.micro). Security group: allow 22 and 80. Download the .pem key.
2. SSH in, run `scripts/ec2_setup.sh`. Log out/in.
3. Push to GitHub. On EC2: `git clone <repo-url> ~/crm && cd ~/crm && cp .env.example .env && nano .env`
   (set GROQ_API_KEY, SECRET_KEY, ADMIN_PASSWORD, CSRF_TRUSTED_ORIGINS=http://<EC2-IP>), then `docker compose up -d --build`.
4. Auto-deploy: GitHub > Settings > Secrets > Actions: EC2_HOST, EC2_USER (ec2-user), EC2_SSH_KEY (.pem text). Every push to `main` redeploys.
Private repo: clone on EC2 with a personal access token URL.

## Notes
- Voice: ElevenLabs free tier via ELEVENLABS_API_KEY, else free browser speech. "Call" uses tel:. Real automated phone calls need Twilio (paid).
- Data (SQLite + audio) lives in the `crm_data` Docker volume.
