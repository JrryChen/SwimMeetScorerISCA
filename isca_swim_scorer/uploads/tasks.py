from celery import shared_task
import logging
from typing import Optional, Dict, Any
from django.db import transaction
from django.db.utils import OperationalError
from django.db import connection

from .parser import process_hytek_file
from uploads.models import UploadedFile
from meets.models import Meet

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
            results = process_hytek_file(uploaded_file.file.path, meet)
        except Exception as e:
            logger.error(f"Error processing file {file_id}: {str(e)}")
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

