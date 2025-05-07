from django.urls import path
from . import views

urlpatterns = [
    path('', views.placeholder_view, name='placeholder'),
]

