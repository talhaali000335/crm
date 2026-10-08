from django.conf import settings
from django.db import models

class Contact(models.Model):
    STATUS = [("lead", "Lead"), ("prospect", "Prospect"), ("customer", "Customer"), ("lost", "Lost")]
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    company = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="lead")
    notes = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Document(models.Model):  # knowledge base (RAG corpus)
    title = models.CharField(max_length=160)
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

class ChatThread(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=120, default="New chat")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

class ChatMessage(models.Model):  # per-thread memory + trace metadata
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10)
    content = models.TextField()
    meta = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)

class CallLog(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=200)
    script = models.TextField()
    audio = models.CharField(max_length=200, blank=True)
    grounded = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
