from django.urls import path
from . import views

app_name = 'uploads'

urlpatterns = [
    # Admin-only routes
    path('admin/', views.UploadedFileListView.as_view(), name='upload-list'),
    path('admin/upload/', views.UploadedFileCreateView.as_view(), name='upload-create'),
    path('<int:pk>/delete/', views.delete_file, name='upload-delete'),
    path('delete-all/', views.delete_all_files, name='upload-delete-all'),
    path('<int:pk>/results/', views.get_file_results, name='upload-results'),
    path('<int:pk>/download/', views.download_file, name='upload-download'),
    path('<int:pk>/status/', views.get_file_status, name='upload-status'),
    path('<int:file_id>/export-results/', views.export_results, name='upload-export-results'),
    path('exports/<int:meet_id>/', views.download_export_zip, name='download-export-zip'),
    path('exports-status/<int:meet_id>/', views.get_export_status, name='export-status'),
    path('download-template/', views.download_dryland_template, name='download-dryland-template'),
    # Combined results endpoints
    path('combined-results/', views.get_combined_results, name='combined-results'),
    path('export-combined-results/', views.export_combined_results, name='export-combined-results'),
    path('exports/combined/', views.download_combined_export_zip, name='download-combined-export-zip'),
    path('exports-status/combined/', views.get_combined_export_status, name='combined-export-status'),
    
    # User-friendly routes (no authentication required)
    path('', views.user_upload_view, name='user-upload'),
    path('iframe/', views.user_upload_iframe_view, name='user-upload-iframe'),
    path('status/', views.user_upload_status_view, name='user-upload-status'),
    path('download/<int:file_id>/', views.user_download_results, name='user-download-results'),
    path('file-status/<int:file_id>/', views.user_file_status_api, name='user-file-status'),
    path('view-results/<int:file_id>/', views.user_view_results, name='user-view-results'),
] 