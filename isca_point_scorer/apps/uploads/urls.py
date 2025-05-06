from django.urls import path
from isca_point_scorer.apps.uploads.views import UploadFileView, UploadListView, UploadDetailView

urlpatterns = [
    path('upload/', UploadFileView.as_view(), name='upload_file'),
    path('uploads/', UploadListView.as_view(), name='upload_list'),
    path('uploads/<int:pk>/', UploadDetailView.as_view(), name='upload_detail'),
]