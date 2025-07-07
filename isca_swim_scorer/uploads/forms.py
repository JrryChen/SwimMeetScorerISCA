from django import forms
from uploads.models import UploadedFile
import os
import zipfile

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

        if not file:
            raise forms.ValidationError('No file was uploaded')

        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('File size must be less than 10MB')
        
        ext = os.path.splitext(file.name)[1].lower()
        
        # Validate file extension matches selected type
        if file_type == 'HY3' and ext != '.hy3':
            raise forms.ValidationError('When selecting HY3 file type, you must upload a .hy3 file')
        elif file_type == 'ZIP' and ext != '.zip':
            raise forms.ValidationError('When selecting ZIP file type, you must upload a .zip file')
        
        # Validate file content (magic number validation)
        if file_type == 'ZIP':
            try:
                # Reset file pointer to beginning
                file.seek(0)
                # Check if it's a valid ZIP file by reading magic bytes
                magic_bytes = file.read(4)
                file.seek(0)  # Reset again
                
                # ZIP file magic signatures
                zip_signatures = [
                    b'PK\x03\x04',  # Standard ZIP
                    b'PK\x05\x06',  # Empty ZIP
                    b'PK\x07\x08'   # Spanned ZIP
                ]
                
                if not any(magic_bytes.startswith(sig) for sig in zip_signatures):
                    raise forms.ValidationError('File does not appear to be a valid ZIP archive')
                
                # Additional validation: try to open as ZIP
                try:
                    with zipfile.ZipFile(file, 'r') as zip_ref:
                        # Just test that we can read the file list
                        zip_ref.namelist()
                except zipfile.BadZipFile:
                    raise forms.ValidationError('File is corrupted or not a valid ZIP archive')
                finally:
                    file.seek(0)  # Reset file pointer
                    
            except Exception as e:
                raise forms.ValidationError('Error validating ZIP file format')
        
        elif file_type == 'HY3':
            # For HY3 files, check if it's a text file (basic validation)
            try:
                file.seek(0)
                sample = file.read(100)  # Read first 100 bytes
                file.seek(0)  # Reset
                
                # Check if it's readable as text (basic check for HY3 format)
                try:
                    sample.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        sample.decode('latin-1')
                    except UnicodeDecodeError:
                        raise forms.ValidationError('HY3 file does not appear to be a valid text file')
                        
            except Exception as e:
                raise forms.ValidationError('Error validating HY3 file format')
        
        return file
    
    
        
