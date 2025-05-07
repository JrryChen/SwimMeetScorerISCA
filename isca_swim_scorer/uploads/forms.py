from django import forms
from uploads.models import UploadedFile

class UploadFileForm(forms.Form):
    """
    Form for uploading a file
    """

    file = forms.FileField(label='Select a file to upload', help_text='Supported file types: .hy3, .cl2, .zip (Max size: 10MB)')

    def clean_file(self):
        file = self.cleaned_data.get('file')

        if file and file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 10MB')
        
        ext = os.path.splitext(file.name)[1].lower()
        valid_extensions = ['.hy3', '.cl2', '.zip']

        if ext not in valid_extensions:
            raise forms.ValidationError('Invalid file type. Supported types: .hy3, .cl2, .zip')
        
        return file
    
    
        
