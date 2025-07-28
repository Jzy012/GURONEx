from django import forms
from .models import Account

class LoginForm(forms.Form):
    email = forms.EmailField(label='Email', max_length=255)
    password = forms.CharField(widget=forms.PasswordInput)



class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(label="Enter your email", max_length=254)


class OTPVerificationForm(forms.Form):
    email = forms.EmailField(label="Email", max_length=254)
    otp = forms.CharField(label="OTP", max_length=6)



class TwoFactorOTPVerificationForm(forms.Form):
    otp = forms.CharField(
        label='Enter OTP',
        max_length=6,
        widget=forms.TextInput(attrs={'placeholder': '6-digit code'})
    )



class PasswordResetForm(forms.Form):
    new_password = forms.CharField(
        label="New password", 
        widget=forms.PasswordInput,
        min_length=8
    )
    confirm_password = forms.CharField(
        label="Confirm new password", 
        widget=forms.PasswordInput,
        min_length=8
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("new_password")
        confirm = cleaned_data.get("confirm_password")
        if password and confirm and password != confirm:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data
    


class TwoFactorToggleForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['two_factor_authentication']
        labels = {
            'two_factor_authentication': 'Enable Two-Factor Authentication (2FA)',
        }





# faculty/forms.py
from django import forms
from base.models import Account
from faculty.models import FacultyProfile, EmploymentStatus
import secrets

class FacultyCreationForm(forms.Form):
    name = forms.CharField(max_length=255)
    email = forms.EmailField()
    department = forms.CharField(max_length=100)
    birth_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    contact_number = forms.CharField(max_length=20, required=False)
    status = forms.ModelChoiceField(queryset=EmploymentStatus.objects.filter(is_active=True), required=False)

    # Password options
    password = forms.CharField(max_length=128, required=False, widget=forms.PasswordInput, help_text="Leave blank to auto-generate.")
    
    def clean_email(self):
        email = self.cleaned_data['email']
        if Account.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def generate_random_password(self):
        return ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))








from django import forms
from faculty.models import DocumentCategory
import os

class FacultyDocumentUploadForm(forms.Form):
    document_category = forms.ModelChoiceField(queryset=DocumentCategory.objects.all(), required=True)
    document_name = forms.CharField(max_length=255, required=True)
    file = forms.FileField(required=True)
    expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        self.faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("document_category")
        file = cleaned_data.get("file")
        expiry = cleaned_data.get("expiry_date")

        if file and category:
            ext = os.path.splitext(file.name)[1].lower().lstrip('.')
            allowed = category.allowed_file_types.values_list("extension", flat=True)
            if ext not in allowed:
                raise forms.ValidationError(f"File type '.{ext}' is not allowed for {category.name}.")

        if category and category.requires_expiry_date and not expiry:
            raise forms.ValidationError("Expiry date is required for this document category.")





# adminhub/forms.py

from django import forms
from adminhub.models import Announcement

ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('faculty', 'Faculty'),
    ('applicant', 'Applicant'),
]

class AnnouncementForm(forms.ModelForm):
    visible_to_roles = forms.MultipleChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Visible To"
    )

    class Meta:
        model = Announcement
        fields = [
            'title', 'content', 'visible_to_roles', 'is_important',
            'send_email', 'attachment_link', 'start_date', 'end_date',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
