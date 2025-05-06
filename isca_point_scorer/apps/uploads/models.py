import os
import uuid
from django.db import models
from django.conf import settings

from isca_point_scorer.apps.core.models import TimeStampedModel
from isca_point_scorer.apps.meets.models import Meet

def upload_path(instance, filename):
    """Generate a file path for uploaded files"""
    ext = os.path.splitext(filename)[1]
    new_filename = f"{uuid.uuid4()}{ext}"
    return os.path.join('uploads', 'meet_files', new_filename)

class UploadedFile(TimeStampedModel):
    """
    Represents a file uploaded by a user.
    """
    FILE_TYPES = (
        ('HY3', 'HY3 - Meet Manager Export'),
        ('CL2', 'CL2 - Results Export'),
        ('ZIP', 'ZIP - Compressed File'),
        ('OTHER', 'Other File Type'),
    )
    
    SOURCE_TYPES = (
        ('WEB', 'Web Upload'),
        ('EMAIL', 'Email Attachment'),
        ('API', 'API Upload'),
    )
    
    file = models.FileField(upload_to=upload_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FILE_TYPES)
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPES, default='WEB')
    
    # Email specific fields
    email_from = models.EmailField(blank=True)
    email_subject = models.CharField(max_length=255, blank=True)
    email_received_at = models.DateTimeField(null=True, blank=True)
    
    # Processing status
    is_processed = models.BooleanField(default=False)
    processing_errors = models.TextField(blank=True)
    meet = models.ForeignKey(Meet, on_delete=models.SET_NULL, null=True, blank=True, related_name='files')
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return self.original_filename
    
    @property
    def file_extension(self):
        return os.path.splitext(self.original_filename)[1].lower()
    
    @property
    def file_size_kb(self):
        if self.file:
            return self.file.size / 1024
        return 0