from celery import shared_task
import logging
from typing import Optional, Dict, Any
from django.db import transaction
from django.db.utils import OperationalError
from django.db import connection
import tempfile
import os
import csv
import zipfile
from datetime import datetime
from django.core.files import File
from django.conf import settings

from .parser import process_hytek_file
from uploads.models import UploadedFile
from meets.models import Meet, Event, Result, Swimmer
from core.utils import format_swim_time

logger = logging.getLogger(__name__)

@shared_task
def debug_shared_task():
    logger.info("Debug task executed successfully")
    return "Debug task completed"

@shared_task(bind=True, max_retries=3)
def process_hytek_file_task(self, file_id: int, meet_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Process a Hytek file asynchronously.
    
    Args:
        file_id: ID of the UploadedFile instance
        meet_id: Optional ID of the associated meet
        
    Returns:
        Dict containing processing results or error information
    """
    try:
        # Close any existing database connections
        connection.close()
        
        # Get the uploaded file instance
        try:
            uploaded_file = UploadedFile.objects.get(id=file_id)
        except UploadedFile.DoesNotExist:
            logger.error(f"UploadedFile with ID {file_id} not found")
            return {
                'status': 'error',
                'error': f"UploadedFile with ID {file_id} not found"
            }
        
        # Get the meet instance
        try:
            meet = Meet.objects.get(id=meet_id) if meet_id else None
        except Meet.DoesNotExist:
            logger.error(f"Meet with ID {meet_id} not found")
            return {
                'status': 'error',
                'error': f"Meet with ID {meet_id} not found"
            }
        
        # Process the file
        try:
            # Check if file is a ZIP and extract if needed
            file_path = uploaded_file.file.path
            if uploaded_file.file_type == 'ZIP':
                logger.info(f"Processing ZIP file: {uploaded_file.original_filename}")
                try:
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        # Find all HY3 files in the ZIP with security validation
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
                            raise ValueError("ZIP archive contains multiple HY3 files. Please include only one HY3 file.")
                        
                        # Extract the HY3 file to a temporary directory safely
                        temp_dir = tempfile.mkdtemp()
                        extracted_path = zip_ref.extract(hy3_files[0], temp_dir)
                        # Additional safety check for the extracted path
                        if not extracted_path.startswith(temp_dir):
                            raise ValueError("Unsafe extraction path detected")
                        file_path = extracted_path
                        logger.info(f"Extracted HY3 file to: {file_path}")
                except zipfile.BadZipFile:
                    raise ValueError("Invalid ZIP file format")
                except Exception as e:
                    raise ValueError(f"Error processing ZIP file: {str(e)}")
            
            results = process_hytek_file(file_path, meet)
            
            # Clean up temporary directory if it was created
            if uploaded_file.file_type == 'ZIP' and 'temp' in file_path:
                import shutil
                try:
                    temp_dir = os.path.dirname(file_path)
                    if os.path.exists(temp_dir) and temp_dir != '/' and 'temp' in temp_dir:
                        shutil.rmtree(temp_dir)
                        logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error processing file {file_id}: {str(e)}")
            # Update the uploaded file with the error
            uploaded_file.processing_errors = str(e)
            uploaded_file.save()
            raise
        
        # Update the uploaded file status
        try:
            with transaction.atomic():
                uploaded_file.is_processed = True
                uploaded_file.save()
        except OperationalError as e:
            logger.error(f"Database error while updating file status: {str(e)}")
            # Retry the task with exponential backoff
            self.retry(exc=e, countdown=2 ** self.request.retries)
            return {
                'status': 'error',
                'error': 'Database error, retrying...'
            }
        
        logger.info(f"Successfully processed file: {uploaded_file.original_filename}")
        return {
            'status': 'success',
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Error processing file {file_id}: {str(e)}")
        # Retry the task with exponential backoff
        self.retry(exc=e, countdown=2 ** self.request.retries)
        return {
            'status': 'error',
            'error': str(e)
        }

@shared_task(bind=True, max_retries=3)
def export_meet_results_task(self, meet_id: int) -> Dict[str, Any]:
    """
    Export meet results to CSV files asynchronously and save to exports directory.
    """
    try:
        connection.close()
        try:
            meet = Meet.objects.get(id=meet_id)
        except Meet.DoesNotExist:
            logger.error(f"Meet with ID {meet_id} not found")
            return {'status': 'error', 'error': f"Meet with ID {meet_id} not found"}

        # Prepare export directory and file path
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        zip_filename = f"meet_{meet_id}_results.zip"
        zip_path = os.path.join(export_dir, zip_filename)

        with tempfile.TemporaryDirectory() as temp_dir:
            by_event_file = os.path.join(temp_dir, "results_by_event.csv")
            by_swimmer_file = os.path.join(temp_dir, "results_by_swimmer.csv")

            # Write results by event
            with open(by_event_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Event', 'Swimmer', 'Age', 'Team', 'Prelim Time', 'Prelim Points',
                                 'Swimoff Time', 'Swimoff Points', 'Final Time', 'Final Points', 'Best Points'])
                # Optimize queries with select_related and prefetch_related
                for event in meet.events.select_related('meet').prefetch_related(
                    'results__swimmer__team'
                ).order_by('event_number'):
                    for result in event.results.all().order_by('final_place', 'prelim_place', 'swim_off_place'):
                        writer.writerow([
                            event.name,
                            result.swimmer.full_name,
                            result.swimmer.age or 'N/A',
                            result.swimmer.team.name,
                            format_swim_time(result.prelim_time) if result.prelim_time else '-',
                            f"{result.prelim_points:.2f}" if result.prelim_points else '-',
                            format_swim_time(result.swim_off_time) if result.swim_off_time else '-',
                            f"{result.swim_off_points:.2f}" if result.swim_off_points else '-',
                            format_swim_time(result.final_time) if result.final_time else '-',
                            f"{result.final_points:.2f}" if result.final_points else '-',
                            f"{result.best_points:.2f}" if result.best_points else '-'
                        ])

            # Write results by swimmer
            with open(by_swimmer_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Swimmer', 'Age', 'Team', 'Event', 'Prelim Time', 'Prelim Points',
                                 'Swimoff Time', 'Swimoff Points', 'Final Time', 'Final Points', 'Best Points'])
                # Optimize queries with select_related and prefetch_related
                for swimmer in meet.swimmers.select_related('team').prefetch_related(
                    'results__event'
                ).order_by('last_name', 'first_name'):
                    for result in swimmer.results.all().order_by('event__event_number'):
                        writer.writerow([
                            swimmer.full_name,
                            swimmer.age or 'N/A',
                            swimmer.team.name,
                            result.event.name,
                            format_swim_time(result.prelim_time) if result.prelim_time else '-',
                            f"{result.prelim_points:.2f}" if result.prelim_points else '-',
                            format_swim_time(result.swim_off_time) if result.swim_off_time else '-',
                            f"{result.swim_off_points:.2f}" if result.swim_off_points else '-',
                            format_swim_time(result.final_time) if result.final_time else '-',
                            f"{result.final_points:.2f}" if result.final_points else '-',
                            f"{result.best_points:.2f}" if result.best_points else '-'
                        ])

            # Create zip file
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(by_event_file, os.path.basename(by_event_file))
                zipf.write(by_swimmer_file, os.path.basename(by_swimmer_file))

        return {'status': 'success', 'zip_path': zip_path, 'zip_filename': zip_filename}
    except Exception as e:
        logger.error(f"Error exporting meet results: {str(e)}")
        self.retry(exc=e, countdown=2 ** self.request.retries)
        return {'status': 'error', 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def export_combined_results_task(self) -> Dict[str, Any]:
    """
    Export combined results from all meets to CSV files asynchronously and save to exports directory.
    """
    try:
        connection.close()
        from meets.models import Meet, Event, Result, Swimmer
        
        export_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        zip_filename = "combined_results.zip"
        zip_path = os.path.join(export_dir, zip_filename)

        with tempfile.TemporaryDirectory() as temp_dir:
            by_event_file = os.path.join(temp_dir, "results_by_event.csv")
            by_swimmer_file = os.path.join(temp_dir, "results_by_swimmer.csv")

            # Write results by event (across all meets)
            with open(by_event_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Meet', 'Event', 'Swimmer', 'Age', 'Team', 'Prelim Time', 'Prelim Points',
                                 'Swimoff Time', 'Swimoff Points', 'Final Time', 'Final Points', 'Best Points'])
                # Optimize queries with select_related and prefetch_related
                for event in Event.objects.select_related('meet').prefetch_related(
                    'results__swimmer__team'
                ).order_by('meet__start_date', 'meet__name', 'event_number'):
                    for result in event.results.all().order_by('final_place', 'prelim_place', 'swim_off_place'):
                        writer.writerow([
                            event.meet.name,
                            event.name,
                            result.swimmer.full_name,
                            result.swimmer.age or 'N/A',
                            result.swimmer.team.name,
                            format_swim_time(result.prelim_time) if result.prelim_time else '-',
                            f"{result.prelim_points:.2f}" if result.prelim_points else '-',
                            format_swim_time(result.swim_off_time) if result.swim_off_time else '-',
                            f"{result.swim_off_points:.2f}" if result.swim_off_points else '-',
                            format_swim_time(result.final_time) if result.final_time else '-',
                            f"{result.final_points:.2f}" if result.final_points else '-',
                            f"{result.best_points:.2f}" if result.best_points else '-'
                        ])

            # Write results by swimmer (across all meets)
            with open(by_swimmer_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Meet', 'Swimmer', 'Age', 'Team', 'Event', 'Prelim Time', 'Prelim Points',
                                 'Swimoff Time', 'Swimoff Points', 'Final Time', 'Final Points', 'Best Points'])
                # Optimize queries with select_related and prefetch_related
                for swimmer in Swimmer.objects.select_related('team').prefetch_related(
                    'results__event__meet'
                ).order_by('last_name', 'first_name'):
                    for result in swimmer.results.all().order_by('event__meet__start_date', 'event__event_number'):
                        writer.writerow([
                            result.event.meet.name,
                            swimmer.full_name,
                            swimmer.age or 'N/A',
                            swimmer.team.name,
                            result.event.name,
                            format_swim_time(result.prelim_time) if result.prelim_time else '-',
                            f"{result.prelim_points:.2f}" if result.prelim_points else '-',
                            format_swim_time(result.swim_off_time) if result.swim_off_time else '-',
                            f"{result.swim_off_points:.2f}" if result.swim_off_points else '-',
                            format_swim_time(result.final_time) if result.final_time else '-',
                            f"{result.final_points:.2f}" if result.final_points else '-',
                            f"{result.best_points:.2f}" if result.best_points else '-'
                        ])

            # Create zip file
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(by_event_file, os.path.basename(by_event_file))
                zipf.write(by_swimmer_file, os.path.basename(by_swimmer_file))

        return {'status': 'success', 'zip_path': zip_path, 'zip_filename': zip_filename}
    except Exception as e:
        logger.error(f"Error exporting combined results: {str(e)}")
        self.retry(exc=e, countdown=2 ** self.request.retries)
        return {'status': 'error', 'error': str(e)}

