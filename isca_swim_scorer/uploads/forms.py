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
        file_type = self.cleaned_data.get('file_type')

        if file and file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 10MB')
        
        ext = os.path.splitext(file.name)[1].lower()
        
        if file_type == 'HY3' and ext != '.hy3':
            raise forms.ValidationError('When selecting HY3 file type, you must upload a .hy3 file')
        elif file_type == 'ZIP' and ext != '.zip':
            raise forms.ValidationError('When selecting ZIP file type, you must upload a .zip file')
        
        return file
    
    
        
