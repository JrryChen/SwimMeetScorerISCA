from django import forms
from uploads.models import UploadedFile
import os

class UploadFileForm(forms.ModelForm):
    """
    Form for uploading a file using the UploadedFile model
    """

    class Meta:
        model = UploadedFile
        fields = ['file', 'file_type', 'source_type']

    def clean_file(self):
        file = self.cleaned_data.get('file')

        if file and file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 10MB')
        
        ext = os.path.splitext(file.name)[1].lower()
        if ext != '.hy3':
            raise forms.ValidationError('Only HY3 files are supported')
        
        return file
    
    
        
