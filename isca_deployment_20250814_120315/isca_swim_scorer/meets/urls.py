from django.urls import path
from . import views

app_name = 'meets'

urlpatterns = [
    path('', views.placeholder_view, name='meet-list'),
]

