"""Lightweight RAG: corpus -> hybrid retrieval (BM25 + TF-IDF cosine, fused by Reciprocal Rank Fusion)
-> LLM re-ranking. Pure Python (no heavy embedding models) so it runs on a free-tier EC2."""
import json, math, re
from collections import Counter
from .models import Contact, CallLog, Document

STOP = set("the a an and or of to in on for with is are was were be this that it as at by from who what which me my".split())

def tok(t):
    out = []
    for w in re.findall(r"[a-z0-9@.+]+", t.lower()):
        w = w.strip(".")
        if len(w) > 3 and w.endswith("s"): w = w[:-1]
        if w and w not in STOP: out.append(w)
    return out

def chunk(text, size=120, overlap=20):
    w = text.split()
    return [" ".join(w[i:i + size]) for i in range(0, max(len(w), 1), size - overlap)] if w else []

def build_corpus(contact_id=None):
    docs = []
    cs = Contact.objects.filter(pk=contact_id) if contact_id else Contact.objects.all()
    if not contact_id:
        by = {}
        for c in cs: by.setdefault(c.status, []).append(c.name)
        docs.append({"id": "overview", "title": "CRM overview",
                     "text": f"CRM overview: {cs.count()} contacts total. " + ". ".join(f"{k} ({len(v)}): {', '.join(v)}" for k, v in by.items())})
    for c in cs:
        docs.append({"id": f"contact:{c.id}", "title": f"Contact: {c.name}",
                     "text": f"{c.name} | email {c.email} | phone {c.phone} | company {c.company} | status {c.status} | notes: {c.notes}"})
    logs = CallLog.objects.select_related("contact").order_by("-id")
    logs = logs.filter(contact_id=contact_id) if contact_id else logs
    for l in logs[:100]:
        docs.append({"id": f"call:{l.id}", "title": f"Call with {l.contact.name} ({l.created:%d %b})", "text": f"{l.purpose}: {l.script}"})
    if not contact_id:
        for d in Document.objects.all():
            for i, ch in enumerate(chunk(d.content)):
                docs.append({"id": f"doc:{d.id}:{i}", "title": f"Doc: {d.title} #{i + 1}", "text": ch})
    return docs

def bm25_scores(q, docs, k1=1.5, b=0.75):
    toks = [tok(d["text"]) for d in docs]; n = len(docs)
    avg = (sum(map(len, toks)) / n) or 1
    df = Counter(w for t in toks for w in set(t)); qt = tok(q); out = []
    for t in toks:
        tf = Counter(t); s = 0.0
        for w in qt:
            if w in tf:
                idf = math.log(1 + (n - df[w] + .5) / (df[w] + .5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        out.append(s)
    return out

def tfidf_scores(q, docs):
    toks = [tok(d["text"]) for d in docs]; n = len(docs)
    df = Counter(w for t in toks for w in set(t))
    idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}
    def vec(t):
        c = Counter(t); v = {w: c[w] * idf.get(w, 0) for w in c}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        return {w: x / norm for w, x in v.items()}
    qv = vec(tok(q))
    return [sum(qv.get(w, 0) * x for w, x in vec(t).items()) for t in toks]

def _ranks(scores):
    order = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: -scores[i])
    return {i: r + 1 for r, i in enumerate(order)}

def retrieve(q, docs, k=8, rrf_k=60):
    """Stage 1: two rankers fused with RRF. Each hit carries both ranks and the fused score."""
    if not docs: return []
    rb, rt = _ranks(bm25_scores(q, docs)), _ranks(tfidf_scores(q, docs)); out = []
    for i, d in enumerate(docs):
        r = sum(1 / (rrf_k + x) for x in (rb.get(i), rt.get(i)) if x)
        out.append({**d, "bm25_rank": rb.get(i), "tfidf_rank": rt.get(i), "rrf": round(r, 4)})
    out.sort(key=lambda c: -c["rrf"])
    return [c for c in out if c["rrf"] > 0][:k] or out[:k]

def rerank(call, q, cands, final_k):
    """Stage 2: LLM cross-scores each (query, passage) pair 0-10; falls back to RRF order on error."""
    try:
        body = "QUERY: " + q + "\n" + "\n".join(f"[{i}] {c['text'][:400]}" for i, c in enumerate(cands))
        raw = call('Score each passage 0-10 for usefulness in answering the QUERY. Reply ONLY JSON {"scores":[...]} '
                   'with exactly one number per passage, in order.', body)
        sc = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["scores"]
        for c, s in zip(cands, sc): c["rerank"] = float(s)
        cands.sort(key=lambda c: (-c.get("rerank", 0), -c["rrf"]))
    except Exception:
        pass
    return cands[:final_k]
