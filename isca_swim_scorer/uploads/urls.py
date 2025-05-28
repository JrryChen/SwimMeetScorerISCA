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
    path('<int:file_id>/export-results/', views.export_results, name='upload-export-results'),
    path('exports/<int:meet_id>/', views.download_export_zip, name='download-export-zip'),
    path('exports-status/<int:meet_id>/', views.get_export_status, name='export-status'),
    # Combined results endpoints
    path('combined-results/', views.get_combined_results, name='combined-results'),
    path('export-combined-results/', views.export_combined_results, name='export-combined-results'),
    path('exports/combined/', views.download_combined_export_zip, name='download-combined-export-zip'),
    path('exports-status/combined/', views.get_combined_export_status, name='combined-export-status'),
] 