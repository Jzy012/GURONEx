from django import forms
from .models import Account

class LoginForm(forms.Form):
    email = forms.EmailField(label='Email', max_length=255)
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Email',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Password',
        })



class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(label="Enter your email", max_length=254)

    def __init__(self, *args, **kwargs):
        super(ForgotPasswordForm, self).__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Email',
        })



class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        label="OTP",
        max_length=6,
        widget=forms.HiddenInput()
    )

    def __init__(self, *args, **kwargs):
        super(OTPVerificationForm, self).__init__(*args, **kwargs)
        self.fields['otp'].widget.attrs.update({
            'class': 'hidden',  # Still required so it's included in the form POST
        })

    def clean_otp(self):
        otp = self.cleaned_data.get("otp")
        if not otp.isdigit() or len(otp) != 6:
            raise forms.ValidationError("OTP must be a 6-digit number.")
        return otp
       




class TwoFactorOTPVerificationForm(forms.Form):
    otp = forms.CharField(
        label='Enter OTP',
        max_length=6,
        widget=forms.TextInput(attrs={'placeholder': '6-digit code'})
    )


from django.contrib.auth.forms import SetPasswordForm

class CustomSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
                'placeholder': field.label
            })




class PasswordResetForm(forms.Form):
    new_password = forms.CharField(
        label="New password", 
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'New password'
        })
    )
    confirm_password = forms.CharField(
        label="Confirm new password", 
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Confirm new password'
        })
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





# forms.py
from django import forms
from faculty.models import DeliverableTemplate, Semester

class AssignDeliverablesForm(forms.Form):
    semester = forms.ModelChoiceField(queryset=Semester.objects.all())
    template = forms.ModelChoiceField(queryset=DeliverableTemplate.objects.all())
    deadline = forms.DateField(widget=forms.SelectDateWidget)






from django import forms
from faculty.models import AcademicYear, Semester
import datetime 



CURRENT_YEAR = datetime.datetime.now().year
YEAR_CHOICES = [(y, f"{y}–{y + 1}") for y in range(CURRENT_YEAR, CURRENT_YEAR + 6)]

class AcademicYearForm(forms.ModelForm):
    academic_year = forms.ChoiceField(
        choices=YEAR_CHOICES,
        label="Academic Year",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = AcademicYear
        fields = ['is_active']  # Only include what's still relevant from the model
        labels = {
            'is_active': 'Active'  # ✅ Rename label here
        }

    def save(self, commit=True):
        instance = super().save(commit=False)

        selected_year = int(self.cleaned_data['academic_year'])
        instance.year_start = selected_year
        instance.year_end = selected_year + 1

        if commit:
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        year_start = int(cleaned_data.get('academic_year'))

        if AcademicYear.objects.filter(year_start=year_start, year_end=year_start + 1).exists():
            raise forms.ValidationError("This academic year already exists.")

class SemesterForm(forms.ModelForm):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True
    )

    class Meta:
        model = Semester
        fields = ['semester_type', 'start_date', 'end_date']



# class AcademicYearForm(forms.ModelForm):
#     class Meta:
#         model = AcademicYear
#         fields = ['year_start', 'year_end', 'is_active']

#     def save(self, commit=True):
#         academic_year = super().save(commit=commit)

#         if commit:
#             if not academic_year.semesters.exists():
#                 # Create 1st Semester
#                 Semester.objects.create(
#                     academic_year=academic_year,
#                     semester_type='1st',
#                     start_date=date(academic_year.year_start, 8, 1),
#                     end_date=date(academic_year.year_start, 12, 31),
#                 )
#                 # Create 2nd Semester
#                 Semester.objects.create(
#                     academic_year=academic_year,
#                     semester_type='2nd',
#                     start_date=date(academic_year.year_end, 1, 1),
#                     end_date=date(academic_year.year_end, 5, 31),
#                 )
#                 # Create Summer Term
#                 Semester.objects.create(
#                     academic_year=academic_year,
#                     semester_type='summer',
#                     start_date=date(academic_year.year_end, 6, 1),
#                     end_date=date(academic_year.year_end, 7, 31),
#                 )
#                 # (Optional) Create Full Year
#                 # Semester.objects.create(
#                 #     academic_year=academic_year,
#                 #     semester_type='full',
#                 #     start_date=date(academic_year.year_start, 8, 1),
#                 #     end_date=date(academic_year.year_end, 7, 31),
#                 # )

#         return academic_year




from django import forms
from faculty.models import DeliverableTemplate, DocumentCategory

class DeliverableTemplateForm(forms.ModelForm):
    document_categories = forms.ModelMultipleChoiceField(
        queryset=DocumentCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Required Documents"
    )

    class Meta:
        model = DeliverableTemplate
        fields = ['name', 'document_categories']





from django import forms
from faculty.models import FacultyDocument, Deliverable, Semester
from django.utils import timezone

class FacultyDeliverableUploadForm(forms.Form):
    deliverable = forms.ModelChoiceField(
        queryset=Deliverable.objects.none(),  # will be set per request
        label="Deliverable",
        empty_label="Select Deliverable"
    )
    file = forms.FileField(label="File")

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop("faculty", None)
        super().__init__(*args, **kwargs)

        if faculty:
            # ✅ NEW: Get active semester only
            active_semester = Semester.objects.filter(is_active=True).first()
            if active_semester:
                self.fields["deliverable"].queryset = Deliverable.objects.filter(
                    semester=active_semester
                ).order_by("document_category__name")

    def clean(self):
        cleaned = super().clean()
        deliverable = cleaned.get("deliverable")

        # Prevent duplicate upload for same deliverable
        if deliverable and FacultyDocument.objects.filter(deliverable=deliverable).exists():
            raise forms.ValidationError("This deliverable has already been uploaded.")
        
        return cleaned
