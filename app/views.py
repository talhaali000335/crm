import json
from django.contrib.auth.decorators import login_not_required
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .conf import MODELS, MODE_LIST
from .models import Contact, ChatThread, CallLog, Document

@login_not_required
def health(request): return HttpResponse("ok")

# Screen 1: dashboard + contacts
def contacts(request):
    if request.method == "POST":
        d = {k: request.POST.get(k, "").strip() for k in ["name", "email", "phone", "company", "status", "notes"]}
        if d["name"]:
            pk = request.POST.get("id")
            if pk: Contact.objects.filter(pk=pk).update(**d)
            else: Contact.objects.create(**d)
        return redirect("contacts")
    q = request.GET.get("q", "")
    qs = Contact.objects.all().order_by("-created")
    if q: qs = qs.filter(Q(name__icontains=q) | Q(company__icontains=q))
    stats = [{"label": l, "n": Contact.objects.filter(status=v).count()} for v, l in Contact.STATUS]
    stats += [{"label": "Calls made", "n": CallLog.objects.count()}, {"label": "Knowledge docs", "n": Document.objects.count()}]
    edit = Contact.objects.filter(pk=request.GET.get("edit") or 0).first()
    return render(request, "contacts.html", {"contacts": qs, "q": q, "edit": edit, "statuses": Contact.STATUS, "stats": stats})

@require_POST
def delete(request, pk):
    get_object_or_404(Contact, pk=pk).delete()
    return redirect("contacts")

# Screen 2: AI workspace (threads, modes, models, RAG options, knowledge base)
def workspace(request, pk=None):
    threads = ChatThread.objects.filter(owner=request.user).order_by("-updated")
    t = threads.filter(pk=pk).first() if pk else None
    hist = [{"role": m.role, "content": m.content, "meta": m.meta} for m in t.messages.order_by("id")] if t else []
    return render(request, "workspace.html", {"threads": threads, "t": t, "hist": hist, "docs": Document.objects.all(),
                  "models": MODELS, "modes": MODE_LIST, "contacts": Contact.objects.all()})

@require_POST
def chat_api(request):
    from .agent import run
    d = json.loads(request.body); text = d.get("message", "").strip()
    if not text: return JsonResponse({"error": "empty"}, status=400)
    t = ChatThread.objects.filter(pk=d.get("thread_id") or 0, owner=request.user).first() or \
        ChatThread.objects.create(owner=request.user, title=text[:40])
    try:
        out = run(t.id, text, d.get("mode", "ask"), d.get("model"), d.get("top_k", 4), d.get("rerank", True),
                  d.get("guardrails", True), int(d.get("contact_id") or 0))
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    t.save()
    return JsonResponse({"thread_id": t.id, "title": t.title, **out})

@require_POST
def thread_rename(request):
    d = json.loads(request.body)
    ChatThread.objects.filter(pk=d.get("id"), owner=request.user).update(title=(d.get("title") or "Chat")[:120])
    return JsonResponse({"ok": True})

@require_POST
def thread_delete(request, pk):
    ChatThread.objects.filter(pk=pk, owner=request.user).delete()
    return redirect("workspace")

@require_POST
def doc_add(request):
    f = request.FILES.get("file")
    content = f.read(200_000).decode("utf-8", "ignore") if f else request.POST.get("content", "")
    title = request.POST.get("title") or (f.name if f else "Untitled")
    if content.strip(): Document.objects.create(title=title[:160], content=content)
    return redirect(request.META.get("HTTP_REFERER") or "workspace")

@require_POST
def doc_delete(request, pk):
    Document.objects.filter(pk=pk).delete()
    return redirect(request.META.get("HTTP_REFERER") or "workspace")

# Screen 3: calls
def calls(request):
    return render(request, "calls.html", {"contacts": Contact.objects.all(), "sel": request.GET.get("contact", ""),
                                          "logs": CallLog.objects.select_related("contact").order_by("-id")[:10]})

@require_POST
def call_api(request):
    from .agent import run
    from .voice import synthesize
    d = json.loads(request.body)
    c = get_object_or_404(Contact, pk=d.get("contact_id"))
    purpose = (d.get("purpose") or "follow-up call")[:200]
    try:
        out = run(0, f"Call script for {c.name}. Purpose: {purpose}", "script", None, 4, False, True, c.id)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    ok = out["verdict"].get("grounded", True)
    audio = synthesize(out["answer"]) if ok else ""
    CallLog.objects.create(contact=c, purpose=purpose, script=out["answer"], audio=audio, grounded=ok)
    return JsonResponse({"script": out["answer"], "audio": audio, "phone": c.phone, "grounded": ok, "note": out["verdict"].get("note", "")})
