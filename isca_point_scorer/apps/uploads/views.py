import os
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.views.generic import FormView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin

from isca_point_scorer.apps.uploads.models import UploadedFile
from isca_point_scorer.apps.uploads.forms import UploadFileForm
from isca_point_scorer.apps.uploads.parser import parse_hy3_file

class UploadFileView(LoginRequiredMixin, FormView):
    template_name = 'uploads/upload.html'
    form_class = UploadFileForm
    
    def form_valid(self, form):
        # Get the uploaded file
        uploaded_file = form.cleaned_data['file']
        
        # Determine file type from extension
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        file_type = 'HY3' if file_extension == '.hy3' else \
                   'CL2' if file_extension == '.cl2' else \
                   'ZIP' if file_extension == '.zip' else 'OTHER'
        
        # Create the uploaded file record
        upload = UploadedFile.objects.create(
            file=uploaded_file,
            original_filename=uploaded_file.name,
            file_type=file_type,
            source_type='WEB'
        )
        
        # Parse the file
        if file_type == 'HY3':
            success, meet, message = parse_hy3_file(upload)
            if success:
                messages.success(self.request, message)
                return redirect('meet_detail', slug=meet.slug)
            else:
                messages.error(self.request, message)
        else:
            messages.warning(self.request, f"File type {file_type} is not supported for parsing.")
        
        return redirect('upload_list')
    
    def get_success_url(self):
        return reverse('upload_list')

class UploadListView(LoginRequiredMixin, ListView):
    model = UploadedFile
    template_name = 'uploads/list.html'
    context_object_name = 'uploads'
    paginate_by = 10
    ordering = ['-created_at']

class UploadDetailView(LoginRequiredMixin, DetailView):
    model = UploadedFile
    template_name = 'uploads/detail.html'
    context_object_name = 'upload'