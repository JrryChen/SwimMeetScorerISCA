from django.urls import path
from . import views

app_name = 'uploads'

urlpatterns = [
    path('', views.UploadedFileListView.as_view(), name='upload-list'),
    path('upload/', views.UploadedFileCreateView.as_view(), name='upload-create'),
    path('<int:pk>/results/', views.get_file_results, name='file-results'),
] 