"""LangGraph pipeline: input_guard -> memory -> retrieve (BM25+TF-IDF+RRF) -> rerank -> generate (Groq)
-> hallucination check -> retry once | safe fallback -> save."""
import json, os, re, time
from typing import TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from . import rag
from .conf import MODELS
from .models import ChatMessage

SAFE = "I can't verify that from the CRM data, so I won't guess. Please check the records."
INJECTION = re.compile(r"ignore (all |any )?(previous|above)|system prompt|reveal your (instructions|prompt)|jailbreak", re.I)
PROMPTS = {
    "ask": "You are a CRM assistant. Answer ONLY from SOURCES and cite them like [S1]. If the answer is not there, say you don't have it.",
    "summary": "Summarize the contact/account the user names: who, status, history, open items. Use ONLY SOURCES; cite [S#].",
    "email": "Draft a concise professional follow-up email (subject + body) for the contact the user names. Use ONLY facts in SOURCES; never invent offers, prices or dates. Sign as [Your name].",
    "next": "Recommend up to 3 next best actions, each justified by SOURCES with citations [S#]. Do not invent facts.",
    "general": "You are a helpful business assistant. No CRM data is available; do not claim facts about specific contacts.",
    "script": "Write a short friendly phone-call script (max 120 words) for a sales rep. Use ONLY facts in SOURCES. Never invent prices, dates or promises.",
}

def llm(model, t=0.2):
    return ChatGroq(model=model, temperature=t, api_key=os.getenv("GROQ_API_KEY"))

def call(model):
    return lambda sys, usr: llm(model, 0).invoke([SystemMessage(content=sys), HumanMessage(content=usr)]).content

class S(TypedDict, total=False):
    thread_id: int; mode: str; model: str; top_k: int; rerank: bool; guardrails: bool; contact_id: int
    user_input: str; history: list; sources: list; cand_n: int; context: str; answer: str
    verdict: dict; retries: int; blocked: bool; t0: float; meta: dict

def input_guard(s):
    if len(s["user_input"]) > 2000 or INJECTION.search(s["user_input"]):
        return {"blocked": True, "answer": "Request blocked by input guardrail.",
                "meta": {"sources": [], "verdict": {"grounded": True, "note": "blocked by input guardrail"}, "trace": {}}}
    return {"blocked": False, "retries": 0}

def memory(s):
    if not s.get("thread_id"): return {"history": []}
    rows = list(ChatMessage.objects.filter(thread_id=s["thread_id"]).order_by("-id")[:10])[::-1]
    return {"history": [(m.role, m.content) for m in rows]}

def retrieve(s):
    if s["mode"] == "general": return {"sources": [], "context": "(none)", "cand_n": 0}
    k = s["top_k"]
    cands = rag.retrieve(s["user_input"], rag.build_corpus(s.get("contact_id") or None), k=max(k * 2, 8))
    n = len(cands)
    if s["rerank"] and s["mode"] != "script" and n > 1: cands = rag.rerank(call(s["model"]), s["user_input"], cands, k)
    else: cands = cands[:k]
    ctx = "\n".join(f"[S{i + 1}] {c['title']}: {c['text']}" for i, c in enumerate(cands)) or "(no data)"
    return {"sources": cands, "context": ctx, "cand_n": n}

def generate(s):
    strict = " Be extra strict: every fact must be copied from SOURCES." if s.get("retries") else ""
    msgs = [SystemMessage(content=f"{PROMPTS[s['mode']]}{strict}\n\nSOURCES:\n{s['context']}")]
    msgs += [HumanMessage(content=c) if r == "user" else AIMessage(content=c) for r, c in s.get("history", [])]
    msgs.append(HumanMessage(content=s["user_input"]))
    return {"answer": llm(s["model"]).invoke(msgs).content.strip()}

def _d(x): return re.sub(r"\D", "", x)

def check(s):
    if not s["guardrails"] or s["mode"] == "general":
        return {"verdict": {"grounded": True, "note": "guardrails off" if not s["guardrails"] else "n/a"}}
    a, ctx = s["answer"], s["context"]
    for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", a):
        if e.lower() not in ctx.lower(): return {"verdict": {"grounded": False, "note": f"unknown email {e}"}}
    for p in re.findall(r"\+?\d[\d\s\-]{6,}\d", a):
        if _d(p) not in _d(ctx): return {"verdict": {"grounded": False, "note": f"unknown phone {p}"}}
    try:
        r = call(s["model"])('You are a strict fact checker. Reply ONLY JSON {"grounded": true|false, "note": "short reason"}. '
            'grounded=true only if every factual claim in ANSWER is supported by SOURCES (greetings/refusals are fine).',
            f"SOURCES:\n{ctx}\n\nANSWER:\n{a}")
        v = json.loads(re.search(r"\{.*\}", r, re.S).group(0))
        return {"verdict": {"grounded": bool(v.get("grounded")), "note": v.get("note", "")}}
    except Exception:
        return {"verdict": {"grounded": False, "note": "checker failed"}}

def retry(s): return {"retries": s.get("retries", 0) + 1}
def fallback(s): return {"answer": SAFE}

def _meta(s):
    srcs = [{**{k: c.get(k) for k in ("id", "title", "bm25_rank", "tfidf_rank", "rrf", "rerank")}, "snippet": c["text"][:160]} for c in s.get("sources", [])]
    return {"sources": srcs, "verdict": s["verdict"],
            "trace": {"latency_ms": int((time.time() - s["t0"]) * 1000), "model": s["model"], "mode": s["mode"],
                      "candidates": s.get("cand_n", 0), "retries": s.get("retries", 0), "rerank": s["rerank"]}}

def save(s):
    m = _meta(s)
    if s.get("thread_id"):
        ChatMessage.objects.create(thread_id=s["thread_id"], role="user", content=s["user_input"])
        ChatMessage.objects.create(thread_id=s["thread_id"], role="assistant", content=s["answer"], meta=m)
    return {"meta": m}

def after_guard(s): return END if s["blocked"] else "memory"
def after_check(s):
    if s["verdict"]["grounded"]: return "save"
    return "retry" if s.get("retries", 0) < 1 else "fallback"

g = StateGraph(S)
for n, f in [("input_guard", input_guard), ("memory", memory), ("retrieve", retrieve), ("generate", generate),
             ("check", check), ("retry", retry), ("fallback", fallback), ("save", save)]:
    g.add_node(n, f)
g.set_entry_point("input_guard")
g.add_conditional_edges("input_guard", after_guard, {"memory": "memory", END: END})
for a, b in [("memory", "retrieve"), ("retrieve", "generate"), ("generate", "check"), ("retry", "generate"), ("fallback", "save"), ("save", END)]:
    g.add_edge(a, b)
g.add_conditional_edges("check", after_check, {"save": "save", "retry": "retry", "fallback": "fallback"})
graph = g.compile()

def run(thread_id, text, mode="ask", model=None, top_k=4, rerank=True, guardrails=True, contact_id=0):
    out = graph.invoke({"thread_id": thread_id, "user_input": text, "mode": mode if mode in PROMPTS else "ask",
                        "model": model if model in MODELS else MODELS[0], "top_k": max(1, min(int(top_k), 8)),
                        "rerank": bool(rerank), "guardrails": bool(guardrails), "contact_id": contact_id, "t0": time.time()})
    m = out["meta"]
    return {"answer": out["answer"], "sources": m["sources"], "verdict": m["verdict"], "trace": m["trace"]}
