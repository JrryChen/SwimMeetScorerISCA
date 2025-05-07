from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.generic import CreateView, ListView
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

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
    success_url = reverse_lazy('upload-list')

    def form_valid(self, form):
        # Set the original filename before saving
        form.instance.original_filename = form.instance.file.name
        response = super().form_valid(form)
        
        # Process the file if it's a HY3 file
        if form.instance.file_type == 'HY3':
            try:
                # Get the full path of the uploaded file
                file_path = form.instance.file.path
                
                # Process the file using our parser
                results = process_hytek_file(file_path)
                
                # Create a new meet if one doesn't exist
                if not form.instance.meet:
                    meet = Meet.objects.create(
                        name=f"Meet from {form.instance.original_filename}",
                        slug=form.instance.original_filename.replace('.hy3', '').lower()
                    )
                    form.instance.meet = meet
                
                # Mark as processed
                form.instance.is_processed = True
                form.instance.save()
                
                messages.success(self.request, 'File processed successfully!')
                
            except Exception as e:
                form.instance.processing_errors = str(e)
                form.instance.save()
                messages.error(self.request, f'Error processing file: {str(e)}')
        
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
        results = process_hytek_file(uploaded_file.file.path)
        
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
