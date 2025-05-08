from django.db import models
import os
import uuid
from core.models import TimeStampedModel
from meets.models import Meet

# Create your models here.

def upload_path(instance, filename):
    """
    Generate a file path for the uploaded file
    """
    ext = os.path.splitext(filename)[1]
    new_filename = f"{uuid.uuid4()}{ext}"
    return os.path.join('uploads', 'meet_files', new_filename)

class UploadedFile(TimeStampedModel):
    """
    Represents a file that was uploaded by a user
    """

    FILE_TYPES = (
        ('HY3', 'HY3 - Meet Manager Export'),
        ('ZIP', 'ZIP - Compressed File (must contain HY3)'),
    )

    SOURCE_TYPES = (
        ('WEB', 'Web Upload'),
        ('EMAIL', 'Email Upload'),
        ('API', 'API Upload'),
        ('OTHER', 'Other Source')
    )

    file = models.FileField(upload_to=upload_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=6, choices=FILE_TYPES)
    source_type = models.CharField(max_length=6, choices=SOURCE_TYPES, default='WEB')

    # processing status
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
    
    
    
