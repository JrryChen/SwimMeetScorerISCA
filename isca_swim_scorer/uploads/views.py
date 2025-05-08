from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import CreateView, ListView, DeleteView
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from datetime import datetime, date
from django.utils.text import slugify
import zipfile
import os
import tempfile

from .models import UploadedFile
from .parser import process_hytek_file
from meets.models import Meet

class UploadedFileListView(ListView):
    model = UploadedFile
    template_name = 'uploads/file_list.html'
    context_object_name = 'files'

class UploadedFileCreateView(CreateView):
    model = UploadedFile
    template_name = 'uploads/file_upload.html'
    fields = ['file', 'file_type', 'source_type']
    success_url = reverse_lazy('uploads:upload-list')

    def get_unique_slug(self, base_slug: str) -> str:
        """Generate a unique slug by appending a timestamp if needed."""
        slug = slugify(base_slug)
        if not Meet.objects.filter(slug=slug).exists():
            return slug
        
        # If slug exists, append timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"{slug}-{timestamp}"

    def extract_hy3_from_zip(self, zip_path):
        """Extract HY3 file from ZIP archive and return its path."""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Find all .hy3 files in the zip
            hy3_files = [f for f in zip_ref.namelist() if f.lower().endswith('.hy3')]
            
            if not hy3_files:
                raise ValueError("No HY3 files found in the ZIP archive")
            
            if len(hy3_files) > 1:
                raise ValueError("Multiple HY3 files found in the ZIP archive. Please upload a ZIP with only one HY3 file.")
            
            # Create a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract the HY3 file
                hy3_filename = hy3_files[0]
                zip_ref.extract(hy3_filename, temp_dir)
                return os.path.join(temp_dir, hy3_filename)

    def form_valid(self, form):
        # Set the original filename before saving
        form.instance.original_filename = form.instance.file.name
        response = super().form_valid(form)
        
        try:
            file_path = form.instance.file.path
            
            # Handle ZIP files
            if form.instance.file_type == 'ZIP':
                if not file_path.lower().endswith('.zip'):
                    raise ValueError("File must be a ZIP archive")
                file_path = self.extract_hy3_from_zip(file_path)
                form.instance.file_type = 'HY3'  # Change type to HY3 after extraction
                form.instance.save()
            
            # Process the file if it's a HY3 file
            if form.instance.file_type == 'HY3':
                # Create a new meet if one doesn't exist
                if not form.instance.meet:
                    # Extract meet name from filename
                    meet_name = form.instance.original_filename.replace('.hy3', '').replace('.zip', '')
                    
                    # Use today's date if we can't extract it from filename
                    meet_date = date.today()
                    try:
                        # Try to extract date from filename if it follows pattern "Meet Name-DDMonYYYY"
                        date_str = meet_name.split('-')[-1]
                        meet_date = datetime.strptime(date_str, '%d%b%Y').date()
                    except (ValueError, IndexError):
                        pass

                    # Generate a unique slug
                    slug = self.get_unique_slug(meet_name)

                    meet = Meet.objects.create(
                        name=meet_name,
                        slug=slug,
                        location="Unknown",  # Default location
                        start_date=meet_date,
                        end_date=meet_date  # Use same date for end_date
                    )
                    form.instance.meet = meet
                    form.instance.save()
                
                # Process the file using our parser
                results = process_hytek_file(file_path, meet=form.instance.meet)
                
                # Mark as processed
                form.instance.is_processed = True
                form.instance.save()
                
                messages.success(self.request, 'File processed successfully!')
            
        except Exception as e:
            form.instance.processing_errors = str(e)
            form.instance.save()
            messages.error(self.request, f'Error processing file: {str(e)}')
        
        return response

class UploadedFileDeleteView(DeleteView):
    model = UploadedFile
    success_url = reverse_lazy('uploads:upload-list')
    template_name = 'uploads/file_confirm_delete.html'

    def delete(self, request, *args, **kwargs):
        # Get the meet associated with this file
        uploaded_file = self.get_object()
        meet = uploaded_file.meet
        
        # Delete the file and its associated meet
        response = super().delete(request, *args, **kwargs)
        
        # If this was the last file for this meet, delete the meet too
        if meet and not UploadedFile.objects.filter(meet=meet).exists():
            meet.delete()
            messages.success(request, 'Meet and all associated files deleted successfully.')
        else:
            messages.success(request, 'File deleted successfully.')
            
        return response

@require_http_methods(["GET"])
def get_file_results(request, pk):
    """API endpoint to get the results of a processed file"""
    try:
        uploaded_file = UploadedFile.objects.get(pk=pk)
        
        if not uploaded_file.is_processed:
            return JsonResponse({
                'error': 'File has not been processed yet'
            }, status=400)
            
        if uploaded_file.file_type != 'HY3':
            return JsonResponse({
                'error': 'File type not supported for results'
            }, status=400)
            
        # Process the file again to get results
        results = process_hytek_file(uploaded_file.file.path, meet=uploaded_file.meet)
        
        return JsonResponse({
            'results': results
        })
        
    except UploadedFile.DoesNotExist:
        return JsonResponse({
            'error': 'File not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)