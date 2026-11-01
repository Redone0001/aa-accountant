from django.urls import path

from accountant import views

app_name = "accountant"
urlpatterns = [
    path("", views.index, name="index"),
    path("dashboard/<int:pk>/", views.dashboard, name="dashboard"),
    path("export/", views.export, name="export"),
    path("sources/", views.sources, name="sources"),
    path("connect/", views.connect, name="connect"),
    path("sources/<int:pk>/sync/", views.sync, name="sync"),
]
