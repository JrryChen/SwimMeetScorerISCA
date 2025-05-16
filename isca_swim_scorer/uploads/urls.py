from django.urls import path
from . import views

app_name = 'uploads'

urlpatterns = [
    path('', views.UploadedFileListView.as_view(), name='upload-list'),
    path('upload/', views.UploadedFileCreateView.as_view(), name='upload-create'),
    path('<int:pk>/delete/', views.delete_file, name='upload-delete'),
    path('delete-all/', views.delete_all_files, name='upload-delete-all'),
    path('<int:pk>/results/', views.get_file_results, name='upload-results'),
    path('<int:pk>/download/', views.download_file, name='upload-download'),
    path('<int:pk>/status/', views.get_file_status, name='upload-status'),
] 