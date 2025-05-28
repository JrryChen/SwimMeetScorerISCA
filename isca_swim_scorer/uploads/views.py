from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import CreateView, ListView, DeleteView
from django.urls import reverse_lazy
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, date
from django.utils.text import slugify
from django.db.models import F
import zipfile
import os
import tempfile
from django.conf import settings

from .models import UploadedFile
from .parser import process_hytek_file
from .tasks import process_hytek_file_task, export_meet_results_task
from meets.models import Meet
from scoring.scoring_system import ScoringSystem
from core.utils import format_swim_time
from core.models import Gender, Stroke, Course

class UploadedFileListView(ListView):
    model = UploadedFile
    template_name = 'uploads/file_list.html'
    context_object_name = 'files'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['download_url'] = reverse_lazy('uploads:upload-download')
        return context

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
            
            # Process the file based on its type
            if form.instance.file_type in ['HY3', 'ZIP']:
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
                
                # Send task to Celery for processing
                task = process_hytek_file_task.delay(form.instance.id, form.instance.meet.id)
                form.instance.celery_task_id = task.id
                form.instance.save()
                
                messages.success(self.request, 'File uploaded successfully! Processing will begin shortly.')
            
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
            
        if uploaded_file.file_type not in ['HY3', 'ZIP']:
            return JsonResponse({
                'error': 'File type not supported for results'
            }, status=400)
            
        # Get results from the database
        meet = uploaded_file.meet
        results = {}
        # scoring = ScoringSystem()
        
        for event in meet.events.all():
            event_results = []
            results_list = []
            
            # First collect all results
            for result in event.results.all():
                # Format times for display
                prelim_time = format_swim_time(result.prelim_time) if result.prelim_time and result.prelim_time > 0 else "-"
                swimoff_time = format_swim_time(result.swim_off_time) if result.swim_off_time and result.swim_off_time > 0 else "-"
                final_time = format_swim_time(result.final_time) if result.final_time and result.final_time > 0 else "-"
                
                # Format age for display
                display_age = "N/A" if not result.swimmer.age or result.swimmer.age == 0 else result.swimmer.age
                
                # Calculate points using None if swimmer age is 0 or None
                # point_age = result.swimmer.age if result.swimmer.age and result.swimmer.age > 0 else None
                
                # # Calculate points for each time type
                # prelim_points = round(scoring.calculate_points(event.event_key, result.prelim_time, point_age, event.max_age, result.swimmer.gender), 2) if result.prelim_time and result.prelim_time > 0 else None
                # swimoff_points = round(scoring.calculate_points(event.event_key, result.swim_off_time, point_age, event.max_age, result.swimmer.gender), 2) if result.swim_off_time and result.swim_off_time > 0 else None
                # final_points = round(scoring.calculate_points(event.event_key, result.final_time, point_age, event.max_age, result.swimmer.gender), 2) if result.final_time and result.final_time > 0 else None
                
                result_data = {
                    'swimmer': result.swimmer.full_name,
                    'age': display_age,
                    'team_code': result.swimmer.team.code if result.swimmer.team else None,
                    'prelim_time': prelim_time,
                    'swimoff_time': swimoff_time,
                    'final_time': final_time,
                    'prelim_points': f"{result.prelim_points:.2f}" if result.prelim_points > 0 else None,
                    'swimoff_points': f"{result.swim_off_points:.2f}" if result.swim_off_points > 0 else None,
                    'final_points': f"{result.final_points:.2f}" if result.final_points > 0 else None,
                    'best_points': f"{result.best_points:.2f}" if result.best_points > 0 else None,
                    # Add raw times for sorting
                    '_final_time': result.final_time if result.final_time and result.final_time > 0 else float('inf'),
                    '_swimoff_time': result.swim_off_time if result.swim_off_time and result.swim_off_time > 0 else float('inf'),
                    '_prelim_time': result.prelim_time if result.prelim_time and result.prelim_time > 0 else float('inf')
                }
                results_list.append(result_data)
            
            # Sort the results
            results_list.sort(key=lambda x: (
                x['_final_time'],
                x['_swimoff_time'],
                x['_prelim_time']
            ))
            
            # Remove the sorting fields and add to final results
            for result in results_list:
                del result['_final_time']
                del result['_swimoff_time']
                del result['_prelim_time']
                event_results.append(result)
                
            results[event.name] = event_results
        
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

@require_http_methods(["GET"])
def download_file(request, pk):
    uploaded_file = get_object_or_404(UploadedFile, pk=pk)
    file_path = uploaded_file.file.path
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=uploaded_file.original_filename)

@require_http_methods(["GET"])
def get_file_status(request, pk):
    """API endpoint to get the processing status of a file"""
    try:
        uploaded_file = UploadedFile.objects.get(pk=pk)
        
        if uploaded_file.is_processed:
            return JsonResponse({
                'status': 'success',
                'message': 'File has been processed'
            })
            
        if uploaded_file.celery_task_id:
            return JsonResponse({
                'status': 'processing',
                'message': 'File is being processed'
            })
            
        return JsonResponse({
            'status': 'pending',
            'message': 'File is pending processing'
        })
        
    except UploadedFile.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error': 'File not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
def delete_file(request, pk):
    """API endpoint to delete a file"""
    try:
        uploaded_file = get_object_or_404(UploadedFile, pk=pk)
        
        # Get the meet associated with this file
        meet = uploaded_file.meet
        
        # Delete the file from storage
        if uploaded_file.file:
            if os.path.isfile(uploaded_file.file.path):
                os.remove(uploaded_file.file.path)
        
        # Delete the database record
        uploaded_file.delete()
        
        # If this was the last file for this meet, delete the meet too
        if meet and not UploadedFile.objects.filter(meet=meet).exists():
            meet.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'File deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
def delete_all_files(request):
    """API endpoint to delete all files"""
    try:
        # Get all files
        files = UploadedFile.objects.all()
        
        # Delete each file from storage
        for file in files:
            if file.file and os.path.isfile(file.file.path):
                os.remove(file.file.path)
        
        # Get all meets that will be orphaned
        meets_to_delete = Meet.objects.filter(files__isnull=True)
        
        # Delete all files from database
        files.delete()
        
        # Delete orphaned meets
        meets_to_delete.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'All files deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

def get_export_zip_path(meet_id):
    export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    zip_filename = f"meet_{meet_id}_results.zip"
    return os.path.join(export_dir, zip_filename)

@require_http_methods(["POST"])
def export_results(request, file_id):
    """API endpoint to export meet results as CSV files or trigger export if missing"""
    try:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
        if not uploaded_file.meet:
            return JsonResponse({'status': 'error', 'error': 'No meet associated with this file'})
        meet_id = uploaded_file.meet.id
        zip_path = get_export_zip_path(meet_id)
        if os.path.exists(zip_path):
            # Already exported, return ready status
            return JsonResponse({'status': 'ready', 'download_url': f'/uploads/exports/{meet_id}/'})
        # Start the export task
        task = export_meet_results_task.delay(meet_id)
        return JsonResponse({'status': 'processing', 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)})

@require_http_methods(["GET"])
def get_export_status(request, meet_id):
    """API endpoint to check if export zip exists for a meet"""
    zip_path = get_export_zip_path(meet_id)
    if os.path.exists(zip_path):
        return JsonResponse({'status': 'ready', 'download_url': f'/uploads/exports/{meet_id}/'})
    return JsonResponse({'status': 'processing'})

@require_http_methods(["GET"])
def download_export_zip(request, meet_id):
    """Download the exported zip file for a meet"""
    zip_path = get_export_zip_path(meet_id)
    if not os.path.exists(zip_path):
        return JsonResponse({'status': 'error', 'error': 'Export file not found'}, status=404)
    
    # Get the meet name for the zip file
    meet = get_object_or_404(Meet, id=meet_id)
    zip_filename = f"{meet.name}_results.zip"
    
    response = FileResponse(open(zip_path, 'rb'), as_attachment=True)
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
    return response

@require_http_methods(["GET"])
def get_task_status(request, task_id):
    """API endpoint to check the status of a Celery task"""
    try:
        # Find the uploaded file with this task ID
        uploaded_file = UploadedFile.objects.get(celery_task_id=task_id)
        
        if uploaded_file.is_processed:
            return JsonResponse({
                'status': 'success',
                'file_id': uploaded_file.id,
                'filename': uploaded_file.original_filename
            })
            
        return JsonResponse({
            'status': 'processing',
            'message': 'Export in progress'
        })
        
    except UploadedFile.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error': 'Task not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

# --- Combined Results Views ---
def get_combined_export_zip_path():
    export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    zip_filename = "combined_results.zip"
    return os.path.join(export_dir, zip_filename)

@require_http_methods(["GET"])
def get_combined_results(request):
    """API endpoint to get combined results from all meets as JSON, grouped by event type and reporting age band."""
    from meets.models import Event, Result
    from core.models import Gender, Stroke, Course
    from collections import defaultdict

    # Define reporting age bands
    def get_reporting_age_band(age):
        if age is None or age < 6:
            return None
        if 6 <= age <= 14:
            return str(age)
        if age >= 15:
            return "15-18+"
        return None

    def event_type_key(event):
        return (
            event.gender,
            event.distance,
            event.stroke,
            event.meet.course,
        )

    def event_type_display(event):
        gender_map = {Gender.MALE: "Men", Gender.FEMALE: "Women", Gender.MIXED: "Mixed", Gender.UNKNOWN: "Unknown"}
        gender_text = gender_map.get(event.gender, "Unknown")
        stroke_display = event.get_stroke_display() if hasattr(event, 'get_stroke_display') else event.stroke
        course_text = f"({event.meet.course})"
        return f"{gender_text} {event.distance} {stroke_display} {course_text}"

    # Gather all results and group by (event type, reporting age band)
    grouped_results = defaultdict(list)
    event_type_names = {}
    for event in Event.objects.all():
        type_key = event_type_key(event)
        if type_key not in event_type_names:
            event_type_names[type_key] = event_type_display(event)
        for result in event.results.all():
            swimmer_age = result.swimmer.age if result.swimmer.age and result.swimmer.age > 0 else None
            age_band = get_reporting_age_band(swimmer_age)
            if not age_band:
                continue  # skip if no valid age
            prelim_time = format_swim_time(result.prelim_time) if result.prelim_time and result.prelim_time > 0 else "-"
            swimoff_time = format_swim_time(result.swim_off_time) if result.swim_off_time and result.swim_off_time > 0 else "-"
            final_time = format_swim_time(result.final_time) if result.final_time and result.final_time > 0 else "-"
            best_time = result.best_time if hasattr(result, 'best_time') else (result.final_time or result.prelim_time or result.swim_off_time or float('inf'))
            result_data = {
                'meet': result.event.meet.name,
                'swimmer': result.swimmer.full_name,
                'age': swimmer_age,
                'team_code': result.swimmer.team.code if result.swimmer.team else None,
                'prelim_time': prelim_time,
                'swimoff_time': swimoff_time,
                'final_time': final_time,
                'prelim_points': f"{result.prelim_points:.2f}" if result.prelim_points > 0 else None,
                'swimoff_points': f"{result.swim_off_points:.2f}" if result.swim_off_points > 0 else None,
                'final_points': f"{result.final_points:.2f}" if result.final_points > 0 else None,
                'best_points': f"{result.best_points:.2f}" if result.best_points > 0 else None,
                '_sort_time': best_time if best_time and best_time > 0 else float('inf'),
            }
            group_label = f"{event_type_names[type_key]} - Age {age_band}"
            grouped_results[group_label].append(result_data)

    # Sort each group by best time
    for group in grouped_results:
        grouped_results[group].sort(key=lambda x: x['_sort_time'])
        for r in grouped_results[group]:
            del r['_sort_time']

    return JsonResponse({'results': grouped_results})

@require_http_methods(["POST"])
def export_combined_results(request):
    """API endpoint to export combined results as CSV/ZIP or trigger export if missing"""
    try:
        zip_path = get_combined_export_zip_path()
        if os.path.exists(zip_path):
            return JsonResponse({'status': 'ready', 'download_url': '/uploads/exports/combined/'})
        from .tasks import export_combined_results_task
        task = export_combined_results_task.delay()
        return JsonResponse({'status': 'processing', 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)})

@require_http_methods(["GET"])
def get_combined_export_status(request):
    zip_path = get_combined_export_zip_path()
    if os.path.exists(zip_path):
        return JsonResponse({'status': 'ready', 'download_url': '/uploads/exports/combined/'})
    return JsonResponse({'status': 'processing'})

@require_http_methods(["GET"])
def download_combined_export_zip(request):
    zip_path = get_combined_export_zip_path()
    if not os.path.exists(zip_path):
        return JsonResponse({'status': 'error', 'error': 'Export file not found'}, status=404)
    zip_filename = "combined_results.zip"
    response = FileResponse(open(zip_path, 'rb'), as_attachment=True)
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
    return response