from django.shortcuts import render
from django.http import HttpResponse

def placeholder_view(request):
    return HttpResponse("Hello, World!")

# Create your views here.
