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
    contact_number = forms.CharField(max_length=11, required=False)
    status = forms.ModelChoiceField(queryset=EmploymentStatus.objects.filter(is_active=True), required=False)
    password = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.PasswordInput,
        help_text="Leave blank to auto-generate."
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label
        # If you want to customize select or date widgets further, you can do so here

    def clean_email(self):
        email = self.cleaned_data['email']
        if Account.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def generate_random_password(self):
        return ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))



from django import forms
from base.models import Account
from faculty.models import FacultyProfile, EmploymentStatus


class FacultyEditForm(forms.ModelForm):
    email = forms.EmailField(
        label='Email',
        max_length=255,
        widget=forms.EmailInput()
    )

    class Meta:
        model = FacultyProfile
        fields = ['name', 'department', 'birth_date', 'contact_number', 'status']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        account_instance = kwargs.pop('account_instance', None)
        super().__init__(*args, **kwargs)
        self.fields['status'].queryset = EmploymentStatus.objects.filter(is_active=True)
        if account_instance:
            self.fields['email'].initial = account_instance.email

        # Style each field
        self.fields['email'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Email',
        })
        self.fields['name'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Full Name',
        })
        self.fields['department'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Department',
        })
        self.fields['birth_date'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Birth Date',
        })
        self.fields['contact_number'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
            'placeholder': 'Contact Number',
        })
        self.fields['status'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-[#800505]',
        })

    def save(self, commit=True):
        faculty_profile = super().save(commit=False)
        if commit:
            faculty_profile.save()
        return faculty_profile








from django import forms
from faculty.models import DocumentCategory
import os

class FacultyDocumentUploadForm(forms.Form):
    document_category = forms.ModelChoiceField(queryset=DocumentCategory.objects.all(), required=True)
    document_name = forms.CharField(max_length=255, required=True)
    file = forms.FileField(required=True)
    expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        index = kwargs.pop("index", None)  # <-- NEW: get index for unique file input id
        self.faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)

        input_class = 'w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505]'

        self.fields['document_category'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Category',
        })
        self.fields['document_name'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Document Name',
        })
        # --- CHANGED: dynamic id for each file input, for formset support
        file_id = f'file_input_{index}' if index is not None else 'file_input__empty'
        self.fields['file'].widget.attrs.update({
            'class': 'hidden',
            'id': file_id,
            'placeholder': 'Select File',
        })
        self.fields['expiry_date'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Expiry Date',
        })

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            # Don't style CheckboxSelectMultiple as input
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs["class"] = field_class
                field.widget.attrs["placeholder"] = field.label
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "rounded text-[#800505] focus:ring-[#800505]"
        # Add custom class to checklist for template targeting
        if "visible_to_roles" in self.fields:
            self.fields["visible_to_roles"].widget.attrs["class"] = "custom-checklist"





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


from django.forms import BaseFormSet

class IndexedFormSet(BaseFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.index = index  # Optional, for debugging or template use

    def _construct_form(self, i, **kwargs):
        kwargs['index'] = i
        return super()._construct_form(i, **kwargs)


from django import forms
from faculty.models import FacultyDocument, Deliverable, Semester
from django.utils import timezone

class FacultyDeliverableUploadForm(forms.Form):
    deliverable = forms.ModelChoiceField(
        queryset=Deliverable.objects.none(),
        label="Deliverable",
        empty_label="Select Deliverable"
    )
    file = forms.FileField(label="File")

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop("faculty", None)
        index = kwargs.pop('index', None)  # <- get index if available
        super().__init__(*args, **kwargs)

        # Add Tailwind classes for reference-style inputs
        self.fields['deliverable'].widget.attrs.update({
            'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505]',
        })
        file_id = f'file_input_{index}' if index is not None else 'file_input__empty'
        self.fields['file'].widget.attrs.update({
            'class': 'hidden',
            'id': file_id,
        })

        # Only show deliverables not yet uploaded or previously rejected
        if faculty:
            active_semester = Semester.objects.filter(is_active=True).first()
            if active_semester:
                already_uploaded = FacultyDocument.objects.filter(
                    faculty=faculty,
                    semester=active_semester
                ).exclude(status='Rejected').values_list('deliverable_id', flat=True)

                self.fields["deliverable"].queryset = Deliverable.objects.filter(
                    semester=active_semester
                ).exclude(id__in=already_uploaded).order_by("document_category__name")

    def clean(self):
        cleaned = super().clean()
        deliverable = cleaned.get("deliverable")
        # Only block if not rejected
        if deliverable and FacultyDocument.objects.filter(deliverable=deliverable).exclude(status='Rejected').exists():
            raise forms.ValidationError("This deliverable has already been uploaded and is not rejected.")
        return cleaned



from django import forms
from faculty.models import RequestType, FacultyRequest, FacultyProfile

class RequestTypeForm(forms.ModelForm):
    class Meta:
        model = RequestType
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label


class FacultyRequestForm(forms.ModelForm):
    class Meta:
        model = FacultyRequest
        fields = ["request_type", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label


class AdminFacultyRequestForm(forms.ModelForm):
    faculty = forms.ModelChoiceField(
        queryset=FacultyProfile.objects.all(),
        required=True
    )

    class Meta:
        model = FacultyRequest
        fields = ["faculty", "request_type", "description", "status", "remarks"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label





##################
#Applicants Forms#
##################


from django import forms
from applicant.models import Applicant, ApplicantDocument, ApplicantRequiredDocument
from faculty.models import DocumentCategory



class ApplicantForm(forms.ModelForm):
    class Meta:
        model = Applicant
        fields = [
            "first_name", "last_name", "suffix", "email", "contact_number",
            "department", "birth_date", "emergency_contact_name", "emergency_contact_number"
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label

        # Optionally, add a more specific placeholder for contact number
        self.fields['contact_number'].widget.attrs["placeholder"] = "e.g. 09XXXXXXXXX"

  


from django import forms
from applicant.models import ApplicantDocument

class ApplicantDocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ApplicantDocument
        fields = ["document_category", "file", "expiry_date", "remarks"]

    def __init__(self, *args, required_doc_cats=None, fixed_document_category=None, index=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_document_category = fixed_document_category

        if self.fixed_document_category:
            self.fields.pop("document_category", None)
            self.instance.document_category = self.fixed_document_category
        elif required_doc_cats is not None:
            self.fields["document_category"].queryset = required_doc_cats

        doc_cat = self.fixed_document_category or self.initial.get("document_category")
        if doc_cat and getattr(doc_cat, "requires_expiry_date", False):
            self.fields["expiry_date"].required = True

        # Hide file input, assign unique id for JS/label targeting
        file_id = f'file_input_{index}' if index is not None else 'file_input__empty'
        existing_class = self.fields['file'].widget.attrs.get('class', '')
        self.fields['file'].widget.attrs.update({
            'class': (existing_class + ' hidden').strip(),
            'id': file_id,
            'placeholder': 'Select File',
        })



from django import forms
from faculty.models import TeachingAssignment

class TeachingAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeachingAssignment
        fields = [
             'subject_code', 'subject_description', 'year_section',
            'day_of_week', 'start_time', 'end_time', 'semester'
        ]
        widgets = {
            'start_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
            'end_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        }



class TeachingAssignmentBulkUploadForm(forms.Form):
    file = forms.FileField(help_text="Upload CSV or Excel file")