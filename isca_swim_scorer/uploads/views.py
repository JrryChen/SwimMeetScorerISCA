from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, ListView, DeleteView
from django.urls import reverse_lazy
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from datetime import datetime, date
from django.utils.text import slugify
from django.db.models import F
import zipfile
import os
import tempfile
import logging
from django.conf import settings

from .models import UploadedFile
from .parser import process_hytek_file
from .tasks import process_uploaded_file_task, export_meet_results_task
from meets.models import Meet
from scoring.scoring_system import ScoringSystem
from core.utils import format_swim_time, format_dryland_score
from core.models import Gender, Stroke, Course

logger = logging.getLogger(__name__)

# Helper Functions for Export Operations
def get_export_zip_path(meet_id):
    """Generate export zip file path for a specific meet"""
    export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    zip_filename = f"meet_{meet_id}_results.zip"
    return os.path.join(export_dir, zip_filename)

def get_combined_export_zip_path():
    """Generate export zip file path for combined results"""
    export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    zip_filename = "combined_results.zip"
    return os.path.join(export_dir, zip_filename)

def ensure_export_directory():
    """Ensure the export directory exists"""
    export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    os.makedirs(export_dir, exist_ok=True)
    return export_dir

def create_file_response(file_path, filename):
    """Create a file response for download with proper error handling"""
    if not os.path.exists(file_path):
        return JsonResponse({'status': 'error', 'error': 'Export file not found'}, status=404)
    
    try:
        response = FileResponse(open(file_path, 'rb'), as_attachment=True)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except (OSError, IOError) as e:
        logger.error(f"Error serving file {file_path}: {str(e)}")
        return JsonResponse({'status': 'error', 'error': 'Error serving file'}, status=500)

def rate_limit_check(request, action, limit=10, window=3600):
    """
    Simple rate limiting check
    Returns True if rate limit is exceeded
    """
    if not hasattr(request, 'META'):
        return False
        
    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    cache_key = f"rate_limit_{action}_{client_ip}"
    
    current_count = cache.get(cache_key, 0)
    if current_count >= limit:
        return True
    
    cache.set(cache_key, current_count + 1, window)
    return False

@method_decorator(staff_member_required, name='dispatch')
class UploadedFileListView(ListView):
    model = UploadedFile
    template_name = 'uploads/file_list.html'
    context_object_name = 'files'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['download_url'] = reverse_lazy('uploads:upload-download')
        return context

@method_decorator(staff_member_required, name='dispatch')
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
            hy3_files = []
            for filename in zip_ref.namelist():
                # Security: Validate file path to prevent zip slip attacks
                if os.path.isabs(filename) or ".." in filename:
                    raise ValueError(f"Unsafe file path detected: {filename}")
                if filename.lower().endswith('.hy3') and not filename.startswith('/'):
                    hy3_files.append(filename)
            
            if not hy3_files:
                raise ValueError("No HY3 files found in the ZIP archive")
            
            if len(hy3_files) > 1:
                raise ValueError("Multiple HY3 files found in the ZIP archive. Please upload a ZIP with only one HY3 file.")
            
            # Create a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract the HY3 file safely
                hy3_filename = hy3_files[0]
                # Additional safety check for the extracted path
                extracted_path = zip_ref.extract(hy3_filename, temp_dir)
                if not extracted_path.startswith(temp_dir):
                    raise ValueError("Unsafe extraction path detected")
                return extracted_path

    def form_valid(self, form):
        # Rate limiting check for file uploads
        if rate_limit_check(self.request, 'file_upload', limit=5, window=3600):
            messages.error(self.request, 'Upload rate limit exceeded. Please try again later.')
            return self.form_invalid(form)
            
        # Set the original filename before saving
        form.instance.original_filename = form.instance.file.name
        response = super().form_valid(form)
        
        try:
            file_path = form.instance.file.path
            
            # Process the file based on its type
            if form.instance.file_type in ['HY3', 'ZIP', 'XLSX']:
                # Create a new meet if one doesn't exist
                if not form.instance.meet:
                    # Extract meet name from filename
                    meet_name = form.instance.original_filename.replace('.hy3', '').replace('.zip', '').replace('.xlsx', '').replace('.xls', '')
                    
                    # For dryland files, add "Dryland" prefix
                    if form.instance.file_type == 'XLSX':
                        meet_name = f"Dryland Events - {meet_name}"
                    
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
                task = process_uploaded_file_task.delay(form.instance.id, form.instance.meet.id)
                form.instance.celery_task_id = task.id
                form.instance.save()
                
                if form.instance.file_type == 'XLSX':
                    messages.success(self.request, 'Dryland file uploaded successfully! Processing will begin shortly.')
                else:
                    messages.success(self.request, 'File uploaded successfully! Processing will begin shortly.')
            
        except (ValueError, zipfile.BadZipFile, OSError, IOError) as e:
            # Handle specific file processing errors
            form.instance.processing_errors = str(e)
            form.instance.save()
            messages.error(self.request, f'Error processing file: {str(e)}')
        except Exception as e:
            # Log unexpected errors for debugging
            logger.error(f"Unexpected error processing file {form.instance.id}: {str(e)}")
            form.instance.processing_errors = "An unexpected error occurred during file processing"
            form.instance.save()
            messages.error(self.request, 'An unexpected error occurred. Please try again or contact support.')
        
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
@staff_member_required
def get_file_results(request, pk):
    """API endpoint to get the results of a processed file"""
    try:
        uploaded_file = UploadedFile.objects.get(pk=pk)
        
        if not uploaded_file.is_processed:
            return JsonResponse({
                'error': 'File has not been processed yet'
            }, status=400)
            
        if uploaded_file.file_type not in ['HY3', 'ZIP', 'XLSX']:
            return JsonResponse({
                'error': 'File type not supported for results'
            }, status=400)
            
        # Get results from the database with optimized queries
        meet = uploaded_file.meet
        results = {}
        # scoring = ScoringSystem()
        
        # Optimize queries with select_related and prefetch_related
        for event in meet.events.select_related('meet').prefetch_related(
            'results__swimmer__team'
        ).all():
            event_results = []
            results_list = []
            
            # Format age group for display
            age_group = ""
            if event.min_age and event.max_age:
                # If max_age is unrealistically high (like 109), treat as open
                if event.max_age >= 99:
                    age_group = f"{event.min_age} & Over" if event.min_age > 1 else "Open"
                elif event.min_age == event.max_age:
                    age_group = f"{event.min_age}"
                else:
                    age_group = f"{event.min_age}-{event.max_age}"
            elif event.min_age:
                age_group = f"{event.min_age} & Over"
            elif event.max_age and event.max_age < 99:
                age_group = f"Under {event.max_age}"
            else:
                age_group = "Open"
            
            # First collect all results
            for result in event.results.all():
                # Check if this is a dryland event
                is_dryland = event.name.startswith('Men\'s') or event.name.startswith('Women\'s') or event.name.startswith('Dryland -') or event.stroke == 'OTH'
                
                # Format time/score based on event type
                def format_time_or_score(value):
                    if not value or value <= 0:
                        return "-"
                    if is_dryland:
                        return format_dryland_score(value)
                    else:
                        return format_swim_time(value)
                
                # Format times/scores for display
                prelim_time = format_time_or_score(result.prelim_time)
                swimoff_time = format_time_or_score(result.swim_off_time)
                final_time = format_time_or_score(result.final_time)
                
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
                    'prelim_points': f"{result.prelim_points:.2f}" if result.prelim_points > 0 else ("0.00" if result.prelim_time and result.prelim_time > 0 else None),
                    'swimoff_points': f"{result.swim_off_points:.2f}" if result.swim_off_points > 0 else ("0.00" if result.swim_off_time and result.swim_off_time > 0 else None),
                    'final_points': f"{result.final_points:.2f}" if result.final_points > 0 else ("0.00" if result.final_time and result.final_time > 0 else None),
                    'best_points': f"{result.best_points:.2f}" if result.best_points > 0 else ("0.00" if (result.prelim_time and result.prelim_time > 0) or (result.swim_off_time and result.swim_off_time > 0) or (result.final_time and result.final_time > 0) else None),
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
                
            # Include age group in event name (but not for dryland events that already have it)
            if event.name.startswith('Men\'s') or event.name.startswith('Women\'s'):
                event_name_with_age = event.name
            else:
                event_name_with_age = f"{event.name} - {age_group}"
            results[event_name_with_age] = event_results
        
        return JsonResponse({
            'results': results
        })
        
    except UploadedFile.DoesNotExist:
        return JsonResponse({
            'error': 'File not found'
        }, status=404)
    except (OSError, IOError) as e:
        logger.error(f"File system error in get_file_results: {str(e)}")
        return JsonResponse({
            'error': 'File system error occurred'
        }, status=500)
    except Exception as e:
        logger.error(f"Unexpected error in get_file_results: {str(e)}")
        return JsonResponse({
            'error': 'An unexpected error occurred'
        }, status=500)

@require_http_methods(["GET"])
@staff_member_required
def download_file(request, pk):
    uploaded_file = get_object_or_404(UploadedFile, pk=pk)
    file_path = uploaded_file.file.path
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=uploaded_file.original_filename)

@require_http_methods(["GET"])
def download_dryland_template(request):
    """Download the DrylandEventTemplate.xlsx file"""
    template_filename = "DrylandEventTemplate.xlsx"
    template_path = os.path.join(settings.BASE_DIR, template_filename)
    
    if not os.path.exists(template_path):
        return JsonResponse({'status': 'error', 'error': 'Template file not found'}, status=404)
    
    try:
        response = FileResponse(open(template_path, 'rb'), as_attachment=True)
        response['Content-Disposition'] = f'attachment; filename="{template_filename}"'
        return response
    except (OSError, IOError) as e:
        logger.error(f"Error serving template file {template_path}: {str(e)}")
        return JsonResponse({'status': 'error', 'error': 'Error serving template file'}, status=500)

@require_http_methods(["GET"])
@staff_member_required
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
@staff_member_required
def delete_file(request, pk):
    """API endpoint to delete a file"""
    try:
        uploaded_file = get_object_or_404(UploadedFile, pk=pk)
        
        # Get the meet associated with this file
        meet = uploaded_file.meet
        
        # Delete the file from storage
        if uploaded_file.file:
            try:
                if os.path.isfile(uploaded_file.file.path):
                    os.remove(uploaded_file.file.path)
            except OSError as e:
                # File might not exist or permission denied, log it but continue
                print(f"Warning: Could not delete file {uploaded_file.file.path}: {e}")
        
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
@staff_member_required
def delete_all_files(request):
    """API endpoint to delete all files"""
    # Rate limiting for destructive operations
    if rate_limit_check(request, 'delete_all', limit=2, window=3600):
        return JsonResponse({
            'status': 'error',
            'error': 'Delete operation rate limit exceeded. Please try again later.'
        }, status=429)
        
    try:
        # Get all files
        files = UploadedFile.objects.all()
        
        # Delete each file from storage
        for file in files:
            if file.file:
                try:
                    if os.path.isfile(file.file.path):
                        os.remove(file.file.path)
                except OSError as e:
                    # File might not exist or permission denied, log it but continue
                    print(f"Warning: Could not delete file {file.file.path}: {e}")
        
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



@require_http_methods(["POST"])
@staff_member_required
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
@staff_member_required
def get_export_status(request, meet_id):
    """API endpoint to check if export zip exists for a meet"""
    zip_path = get_export_zip_path(meet_id)
    if os.path.exists(zip_path):
        return JsonResponse({'status': 'ready', 'download_url': f'/uploads/exports/{meet_id}/'})
    return JsonResponse({'status': 'processing'})

@require_http_methods(["GET"])
@staff_member_required
def download_export_zip(request, meet_id):
    """Download the exported zip file for a meet"""
    zip_path = get_export_zip_path(meet_id)
    
    # Get the meet name for the zip file
    meet = get_object_or_404(Meet, id=meet_id)
    zip_filename = f"{meet.name}_results.zip"
    
    return create_file_response(zip_path, zip_filename)

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


@require_http_methods(["GET"])
@staff_member_required
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
    # Optimize queries with select_related and prefetch_related
    for event in Event.objects.select_related('meet').prefetch_related(
        'results__swimmer__team'
    ).all():
        type_key = event_type_key(event)
        if type_key not in event_type_names:
            event_type_names[type_key] = event_type_display(event)
        # Format age group for display
        age_group = ""
        if event.min_age and event.max_age:
            # If max_age is unrealistically high (like 109), treat as open
            if event.max_age >= 99:
                age_group = f"{event.min_age}+" if event.min_age > 1 else "Open"
            elif event.min_age == event.max_age:
                age_group = f"{event.min_age}"
            else:
                age_group = f"{event.min_age}-{event.max_age}"
        elif event.min_age:
            age_group = f"{event.min_age}+"
        elif event.max_age and event.max_age < 99:
            age_group = f"Under {event.max_age}"
        else:
            age_group = "Open"
        
        for result in event.results.all():
            swimmer_age = result.swimmer.age if result.swimmer.age and result.swimmer.age > 0 else None
            age_band = get_reporting_age_band(swimmer_age)
            if not age_band:
                continue  # skip if no valid age
                
            # Check if swimmer has any valid time - skip if no results
            has_valid_time = (
                (result.prelim_time and result.prelim_time > 0) or 
                (result.swim_off_time and result.swim_off_time > 0) or 
                (result.final_time and result.final_time > 0)
            )
            if not has_valid_time:
                continue  # skip swimmers with no valid times
                
            # Check if this is a dryland event
            is_dryland = event.name.startswith('Men\'s') or event.name.startswith('Women\'s') or event.name.startswith('Dryland -') or event.stroke == 'OTH'
            
            # Format time/score based on event type
            def format_time_or_score(value):
                if not value or value <= 0:
                    return "-"
                if is_dryland:
                    return format_dryland_score(value)
                else:
                    return format_swim_time(value)
            
            prelim_time = format_time_or_score(result.prelim_time)
            swimoff_time = format_time_or_score(result.swim_off_time)
            final_time = format_time_or_score(result.final_time)
            best_time = result.best_time if hasattr(result, 'best_time') else (result.final_time or result.prelim_time or result.swim_off_time or float('inf'))
            
            # Get the best formatted time for duplicate detection
            best_formatted_time = "-"
            if result.final_time and result.final_time > 0:
                best_formatted_time = final_time
            elif result.prelim_time and result.prelim_time > 0:
                best_formatted_time = prelim_time
            elif result.swim_off_time and result.swim_off_time > 0:
                best_formatted_time = swimoff_time
            
            result_data = {
                'meet': result.event.meet.name,
                'swimmer': result.swimmer.full_name,
                'age': swimmer_age,
                'team_code': result.swimmer.team.code if result.swimmer.team else None,
                'prelim_time': prelim_time,
                'swimoff_time': swimoff_time,
                'final_time': final_time,
                'prelim_points': f"{result.prelim_points:.2f}" if result.prelim_points > 0 else ("0.00" if result.prelim_time and result.prelim_time > 0 else "-"),
                'swimoff_points': f"{result.swim_off_points:.2f}" if result.swim_off_points > 0 else ("0.00" if result.swim_off_time and result.swim_off_time > 0 else "-"),
                'final_points': f"{result.final_points:.2f}" if result.final_points > 0 else ("0.00" if result.final_time and result.final_time > 0 else "-"),
                'best_points': f"{result.best_points:.2f}" if result.best_points > 0 else ("0.00" if (result.prelim_time and result.prelim_time > 0) or (result.swim_off_time and result.swim_off_time > 0) or (result.final_time and result.final_time > 0) else "-"),
                '_sort_time': best_time if best_time and best_time > 0 else float('inf'),
                '_duplicate_key': (result.swimmer.full_name, swimmer_age, result.swimmer.team.code if result.swimmer.team else None, best_formatted_time),
            }
            group_label = f"{event_type_names[type_key]} - {age_group} - Age {age_band}"
            grouped_results[group_label].append(result_data)

    # Remove duplicates and sort each group by best time
    for group in grouped_results:
        # Remove duplicates based on name, age, team, and time
        seen_duplicates = set()
        unique_results = []
        
        for result in grouped_results[group]:
            duplicate_key = result['_duplicate_key']
            if duplicate_key not in seen_duplicates:
                seen_duplicates.add(duplicate_key)
                unique_results.append(result)
        
        # Sort by best time
        unique_results.sort(key=lambda x: x['_sort_time'])
        
        # Clean up temporary keys
        for r in unique_results:
            del r['_sort_time']
            del r['_duplicate_key']
        
        grouped_results[group] = unique_results

    return JsonResponse({'results': grouped_results})

@require_http_methods(["POST"])
@staff_member_required
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
@staff_member_required
def get_combined_export_status(request):
    zip_path = get_combined_export_zip_path()
    if os.path.exists(zip_path):
        return JsonResponse({'status': 'ready', 'download_url': '/uploads/exports/combined/'})
    return JsonResponse({'status': 'processing'})


# User Upload Views (No Authentication Required)
def user_upload_view(request):
    """View for users to upload multiple files and get results"""
    from .forms import UserMultipleFileUploadForm
    
    if request.method == 'POST':
        form = UserMultipleFileUploadForm()  # Empty form since we handle files manually
        files = request.FILES.getlist('files')
        
        # Validate files
        errors = []
        if not files:
            errors.append('Please select at least one file to upload.')
        
        if len(files) > 10:  # Limit to 10 files at once
            errors.append('You can upload a maximum of 10 files at once.')
        
        valid_extensions = ['.hy3', '.zip', '.xlsx']
        
        for file in files:
            # Check file size
            if file.size > 10 * 1024 * 1024:  # 10MB limit
                errors.append(f'File "{file.name}" is too large. Maximum size is 10MB.')
                continue
            
            # Check file extension
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in valid_extensions:
                errors.append(f'File "{file.name}" has an unsupported format. Please upload HY3, ZIP, or XLSX files only.')
                continue
            
            # Basic validation for ZIP files
            if ext == '.zip':
                try:
                    file.seek(0)
                    magic_bytes = file.read(4)
                    file.seek(0)
                    
                    zip_signatures = [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08']
                    if not any(magic_bytes.startswith(sig) for sig in zip_signatures):
                        errors.append(f'File "{file.name}" does not appear to be a valid ZIP archive.')
                        continue
                    
                    # Test ZIP file integrity
                    try:
                        with zipfile.ZipFile(file, 'r') as zip_ref:
                            zip_ref.namelist()
                    except zipfile.BadZipFile:
                        errors.append(f'File "{file.name}" is corrupted or not a valid ZIP archive.')
                        continue
                    finally:
                        file.seek(0)
                except Exception as e:
                    errors.append(f'Error validating ZIP file "{file.name}".')
                    continue
            
            # Basic validation for HY3 files
            elif ext == '.hy3':
                try:
                    file.seek(0)
                    sample = file.read(100)
                    file.seek(0)
                    
                    try:
                        sample.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            sample.decode('latin-1')
                        except UnicodeDecodeError:
                            errors.append(f'File "{file.name}" does not appear to be a valid HY3 text file.')
                            continue
                except Exception as e:
                    errors.append(f'Error validating HY3 file "{file.name}".')
                    continue
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            uploaded_files = []
            
            for file in files:
                # Determine file type based on extension
                ext = os.path.splitext(file.name)[1].lower()
                if ext == '.hy3':
                    file_type = 'HY3'
                elif ext == '.zip':
                    file_type = 'ZIP'  
                elif ext == '.xlsx':
                    file_type = 'XLSX'
                else:
                    continue  # Skip invalid files (should be caught by form validation)
                
                # Create UploadedFile instance
                uploaded_file = UploadedFile.objects.create(
                    file=file,
                    original_filename=file.name,
                    file_type=file_type,
                    source_type='WEB'
                )
                uploaded_files.append(uploaded_file)
                
                # Process HY3, ZIP, and XLSX files automatically
                if file_type in ['HY3', 'ZIP', 'XLSX']:
                    from .tasks import process_uploaded_file_task
                    task = process_uploaded_file_task.delay(uploaded_file.id)
                    uploaded_file.celery_task_id = task.id
                    uploaded_file.save()
            
            # Store uploaded file IDs in session for status tracking
            request.session['uploaded_file_ids'] = [f.id for f in uploaded_files]
            
            messages.success(request, f'Successfully uploaded {len(uploaded_files)} files! Processing has begun.')
            
            # For AJAX requests, return JSON response
            # Debug headers
            logger.info(f"Content-Type: {request.headers.get('Content-Type')}")
            logger.info(f"Accept: {request.headers.get('Accept')}")
            
            # Check if this is an AJAX request expecting JSON
            accepts_json = 'application/json' in request.headers.get('Accept', '')
            is_json_content = request.headers.get('Content-Type') == 'application/json'
            
            logger.info(f"Accepts JSON: {accepts_json}, Is JSON Content: {is_json_content}")
            
            if is_json_content or accepts_json:
                logger.info("Returning JSON response for localStorage persistence")
                uploaded_files_data = [{
                    'id': f.id,
                    'filename': f.original_filename,
                    'file_type': f.file_type,
                    'upload_date': f.created_at.isoformat(),
                    'status': 'pending' if not f.is_processed else 'completed'
                } for f in uploaded_files]
                
                return JsonResponse({
                    'success': True,
                    'message': f'Successfully uploaded {len(uploaded_files)} files! Processing has begun.',
                    'uploaded_files': uploaded_files_data,
                    'processing_count': len([f for f in uploaded_files if f.file_type in ['HY3', 'ZIP', 'XLSX']])
                })
            
            logger.info("Returning redirect response")
            return redirect('uploads:user-upload-status')
    else:
        form = UserMultipleFileUploadForm()
    
    return render(request, 'uploads/user_upload.html', {'form': form})


def user_upload_iframe_view(request):
    """Iframe-friendly upload view for embedding in ISCA website"""
    from .forms import UserMultipleFileUploadForm
    
    if request.method == 'POST':
        form = UserMultipleFileUploadForm()  # Empty form since we handle files manually
        files = request.FILES.getlist('files')
        
        # Validate files (same validation as regular upload view)
        errors = []
        if not files:
            errors.append('Please select at least one file to upload.')
        
        if len(files) > 10:  # Limit to 10 files at once
            errors.append('You can upload a maximum of 10 files at once.')
        
        valid_extensions = ['.hy3', '.zip', '.xlsx']
        
        for file in files:
            # Check file size
            if file.size > 10 * 1024 * 1024:  # 10MB limit
                errors.append(f'File "{file.name}" is too large. Maximum size is 10MB.')
                continue
            
            # Check file extension
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in valid_extensions:
                errors.append(f'File "{file.name}" has an unsupported format. Please upload HY3, ZIP, or XLSX files only.')
                continue
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            uploaded_files = []
            
            for file in files:
                # Determine file type based on extension
                ext = os.path.splitext(file.name)[1].lower()
                if ext == '.hy3':
                    file_type = 'HY3'
                elif ext == '.zip':
                    file_type = 'ZIP'  
                elif ext == '.xlsx':
                    file_type = 'XLSX'
                else:
                    continue  # Skip invalid files
                
                # Create UploadedFile instance
                uploaded_file = UploadedFile.objects.create(
                    file=file,
                    original_filename=file.name,
                    file_type=file_type,
                    source_type='WEB'
                )
                uploaded_files.append(uploaded_file)
                
                # Process HY3, ZIP, and XLSX files automatically
                if file_type in ['HY3', 'ZIP', 'XLSX']:
                    from .tasks import process_uploaded_file_task
                    task = process_uploaded_file_task.delay(uploaded_file.id)
                    uploaded_file.celery_task_id = task.id
                    uploaded_file.save()
            
            # Store uploaded file IDs in session for status tracking
            request.session['uploaded_file_ids'] = [f.id for f in uploaded_files]
            
            messages.success(request, f'Successfully uploaded {len(uploaded_files)} files! Processing has begun.')
            
            # For AJAX requests, return JSON response
            if request.headers.get('Content-Type') == 'application/json' or 'application/json' in request.headers.get('Accept', ''):
                uploaded_files_data = [{
                    'id': f.id,
                    'filename': f.original_filename,
                    'file_type': f.file_type,
                    'upload_date': f.created_at.isoformat(),
                    'status': 'pending' if not f.is_processed else 'completed'
                } for f in uploaded_files]
                
                return JsonResponse({
                    'success': True,
                    'message': f'Successfully uploaded {len(uploaded_files)} files! Processing has begun.',
                    'uploaded_files': uploaded_files_data,
                    'processing_count': len([f for f in uploaded_files if f.file_type in ['HY3', 'ZIP', 'XLSX']])
                })
            
            # For iframe, return success with files data instead of redirect
            context = {
                'form': form,
                'uploaded_files': uploaded_files,
                'upload_success': True,
                'processing_count': len([f for f in uploaded_files if f.file_type in ['HY3', 'ZIP', 'XLSX']])
            }
            return render(request, 'uploads/user_upload_iframe.html', context)
    else:
        form = UserMultipleFileUploadForm()
    
    return render(request, 'uploads/user_upload_iframe.html', {'form': form})


def user_upload_status_view(request):
    """View to show upload status and provide download links when ready"""
    uploaded_file_ids = request.session.get('uploaded_file_ids', [])
    
    # If no session files, try to restore from localStorage via URL parameter
    if not uploaded_file_ids and request.GET.get('restore_files'):
        try:
            restore_ids = [int(id) for id in request.GET.get('restore_files', '').split(',') if id.strip()]
            if restore_ids:
                # Verify these files exist and were uploaded recently (within 24 hours)
                from datetime import datetime, timedelta
                cutoff_time = datetime.now() - timedelta(hours=24)
                restored_files = UploadedFile.objects.filter(
                    id__in=restore_ids, 
                    created_at__gte=cutoff_time
                )
                if restored_files.exists():
                    uploaded_file_ids = [f.id for f in restored_files]
                    request.session['uploaded_file_ids'] = uploaded_file_ids
        except (ValueError, TypeError):
            pass  # Invalid restore data, continue normally
    
    if not uploaded_file_ids:
        return redirect('uploads:user-upload')
    
    uploaded_files = UploadedFile.objects.filter(id__in=uploaded_file_ids)
    
    # Check processing status
    processing_complete = all(
        f.is_processed or f.file_type == 'XLSX' 
        for f in uploaded_files
    )
    
    context = {
        'files': uploaded_files,
        'processing_complete': processing_complete,
    }
    
    response = render(request, 'uploads/user_status.html', context)
    # Add cache-busting headers to prevent template rendering issues
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@require_http_methods(["GET"])
def user_download_results(request, file_id):
    """Download ZIP file containing both by-event and by-swimmer CSV results for a specific file"""
    uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    
    # Only allow download if file is processed and has a meet
    if not uploaded_file.is_processed or not uploaded_file.meet:
        return JsonResponse({'error': 'Results not available'}, status=400)
    
    try:
        from .tasks import export_meet_results_as_zip
        zip_path = export_meet_results_as_zip(uploaded_file.meet.id)
        
        if not zip_path or not os.path.exists(zip_path):
            return JsonResponse({'error': 'Export file not found'}, status=404)
        
        # Create download response
        with open(zip_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/zip')
            filename = f"{uploaded_file.meet.name}_results.zip"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            # Add cache-busting headers
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
            
    except Exception as e:
        logger.error(f"Error generating ZIP for file {file_id}: {str(e)}")
        return JsonResponse({'error': 'Error generating results'}, status=500)


@require_http_methods(["GET"])
def user_file_status_api(request, file_id):
    """API endpoint to check processing status of a user's file"""
    try:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
        
        status = 'pending'
        if uploaded_file.is_processed:
            status = 'completed'
        elif uploaded_file.celery_task_id:
            status = 'processing'
        
        return JsonResponse({
            'status': status,
            'filename': uploaded_file.original_filename,
            'file_type': uploaded_file.get_file_type_display(),
            'can_download': uploaded_file.is_processed and uploaded_file.meet is not None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def user_view_results(request, file_id):
    """API endpoint for users to view results of a processed file"""
    try:
        uploaded_file = get_object_or_404(UploadedFile, id=file_id)
        
        if not uploaded_file.is_processed:
            return JsonResponse({
                'error': 'File has not been processed yet'
            }, status=400)
            
        if uploaded_file.file_type not in ['HY3', 'ZIP', 'XLSX']:
            return JsonResponse({
                'error': 'File type not supported for results'
            }, status=400)
            
        if not uploaded_file.meet:
            return JsonResponse({
                'error': 'No meet data available for this file'
            }, status=400)
        
        # Get results from the database with optimized queries
        meet = uploaded_file.meet
        results = {}
        
        # Optimize queries with select_related and prefetch_related
        for event in meet.events.select_related('meet').prefetch_related(
            'results__swimmer__team'
        ).all():
            event_results = []
            results_list = []
            
            # Format age group for display
            age_group = ""
            if event.min_age and event.max_age:
                # If max_age is unrealistically high (like 109), treat as open
                if event.max_age >= 99:
                    age_group = f"{event.min_age} & Over" if event.min_age > 1 else "Open"
                elif event.min_age == event.max_age:
                    age_group = f"{event.min_age}"
                else:
                    age_group = f"{event.min_age}-{event.max_age}"
            elif event.min_age:
                age_group = f"{event.min_age} & Over"
            elif event.max_age and event.max_age < 99:
                age_group = f"Under {event.max_age}"
            else:
                age_group = "Open"
            
            # Collect all results that have points
            for result in event.results.all():
                # Skip results that don't have any points
                has_points = any([
                    result.prelim_points and result.prelim_points > 0,
                    result.swim_off_points and result.swim_off_points > 0, 
                    result.final_points and result.final_points > 0,
                    result.best_points and result.best_points > 0
                ])
                
                if not has_points:
                    continue
                
                # Check if this is a dryland event
                is_dryland = event.name.startswith('Men\'s') or event.name.startswith('Women\'s') or event.name.startswith('Dryland -') or event.stroke == 'OTH'
                
                # Format time/score based on event type
                def format_time_or_score(value):
                    if not value or value <= 0:
                        return "-"
                    if is_dryland:
                        return format_dryland_score(value)
                    else:
                        return format_swim_time(value)
                
                # Format times/scores for display
                prelim_time = format_time_or_score(result.prelim_time)
                swimoff_time = format_time_or_score(result.swim_off_time)
                final_time = format_time_or_score(result.final_time)
                
                # Format age for display
                display_age = "N/A" if not result.swimmer.age or result.swimmer.age == 0 else result.swimmer.age
                
                result_data = {
                    'swimmer': result.swimmer.full_name,
                    'age': display_age,
                    'team_code': result.swimmer.team.code if result.swimmer.team else None,
                    'prelim_time': prelim_time,
                    'swimoff_time': swimoff_time,
                    'final_time': final_time,
                    'prelim_points': f"{result.prelim_points:.2f}" if result.prelim_points and result.prelim_points > 0 else ("0.00" if result.prelim_time and result.prelim_time > 0 else "-"),
                    'swimoff_points': f"{result.swim_off_points:.2f}" if result.swim_off_points and result.swim_off_points > 0 else ("0.00" if result.swim_off_time and result.swim_off_time > 0 else "-"),
                    'final_points': f"{result.final_points:.2f}" if result.final_points and result.final_points > 0 else ("0.00" if result.final_time and result.final_time > 0 else "-"),
                    'best_points': f"{result.best_points:.2f}" if result.best_points and result.best_points > 0 else ("0.00" if (result.prelim_time and result.prelim_time > 0) or (result.swim_off_time and result.swim_off_time > 0) or (result.final_time and result.final_time > 0) else "-"),
                    # Add raw times and points for sorting
                    '_final_time': result.final_time if result.final_time and result.final_time > 0 else float('inf'),
                    '_swimoff_time': result.swim_off_time if result.swim_off_time and result.swim_off_time > 0 else float('inf'),
                    '_prelim_time': result.prelim_time if result.prelim_time and result.prelim_time > 0 else float('inf'),
                    '_best_points': result.best_points if result.best_points and result.best_points > 0 else 0
                }
                results_list.append(result_data)
            
            # Sort the results based on event type
            if is_dryland:
                # For dryland events, sort by points (highest first)
                results_list.sort(key=lambda x: x['_best_points'], reverse=True)
            else:
                # For swim events, sort by time (fastest first)
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
                del result['_best_points']
                event_results.append(result)
                
            # Only include events that have results with points
            if event_results:
                # For dryland events, the age group is already in the event name
                if event.name.startswith('Men\'s') or event.name.startswith('Women\'s'):
                    event_name_with_age = event.name
                else:
                    event_name_with_age = f"{event.name} - {age_group}"
                results[event_name_with_age] = event_results
        
        return JsonResponse({
            'results': results,
            'meet_name': meet.name
        })
        
    except UploadedFile.DoesNotExist:
        return JsonResponse({
            'error': 'File not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Unexpected error in user_view_results: {str(e)}")
        return JsonResponse({
            'error': 'An unexpected error occurred'
        }, status=500)

@require_http_methods(["GET"])
@staff_member_required
def download_combined_export_zip(request):
    zip_path = get_combined_export_zip_path()
    zip_filename = "combined_results.zip"
    return create_file_response(zip_path, zip_filename)