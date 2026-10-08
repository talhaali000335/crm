from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_not_required
from django.urls import path
from . import views as v
urlpatterns = [
    path("login/", login_not_required(auth.LoginView.as_view(template_name="login.html")), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("health/", v.health),
    path("", v.contacts, name="contacts"),
    path("delete/<int:pk>/", v.delete, name="delete"),
    path("workspace/", v.workspace, name="workspace"),
    path("workspace/<int:pk>/", v.workspace, name="thread"),
    path("api/chat/", v.chat_api),
    path("api/thread/rename/", v.thread_rename),
    path("thread/<int:pk>/delete/", v.thread_delete, name="thread_delete"),
    path("docs/add/", v.doc_add, name="doc_add"),
    path("docs/<int:pk>/delete/", v.doc_delete, name="doc_delete"),
    path("calls/", v.calls, name="calls"),
    path("api/call/", v.call_api),
]
