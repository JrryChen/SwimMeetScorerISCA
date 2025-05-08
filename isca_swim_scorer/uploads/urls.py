from django.urls import path
from . import views

app_name = 'uploads'

urlpatterns = [
    path('', views.UploadedFileListView.as_view(), name='upload-list'),
    path('upload/', views.UploadedFileCreateView.as_view(), name='upload-create'),
    path('<int:pk>/delete/', views.UploadedFileDeleteView.as_view(), name='upload-delete'),
    path('<int:pk>/results/', views.get_file_results, name='upload-results'),
] 