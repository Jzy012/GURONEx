import os
import re
import secrets
import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.forms import BaseFormSet, BaseModelFormSet
from django.utils import timezone
from django.contrib.auth.forms import SetPasswordForm, PasswordChangeForm

from base.models import Account, LandingAppearance

from faculty.models import (
    FacultyProfile,
    EmploymentStatus,
    DocumentCategory,
    FileType,
    DeliverableTemplate,
    Deliverable,
    FacultyDocument,
    Semester,
    AcademicYear,
    TeachingAssignment,
    RequestType,
    FacultyRequest,
    phone_validator,
    name_part_validator,
)

from applicant.models import Applicant, ApplicantDocument, ApplicantRequiredDocument, AreaOfSpecialization

from rfid.models import AttendanceLog

from adminhub.models import Announcement, PUPSite


def _normalize_ph_mobile(value: str) -> str:
    """Normalize and validate a PH mobile number. Strips JS-inserted spaces, then checks format."""
    value = (value or "").strip()
    if not value:
        return ""
    normalized = value.replace(" ", "")
    if not normalized.isdigit():
        raise forms.ValidationError("Contact number must contain numbers only.")
    if len(normalized) != 11:
        raise forms.ValidationError("Please enter a valid 11-digit mobile number.")
    if not normalized.startswith("09"):
        raise forms.ValidationError("Please enter a valid Philippine mobile number starting with 09.")
    return normalized


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
            'class': 'hidden', 
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



class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs.update({
                'class': 'w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-[#800505] text-base'
            })



class TwoFactorToggleForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['two_factor_authentication']
        labels = {
            'two_factor_authentication': 'Enable Two-Factor Authentication (2FA)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['two_factor_authentication'].widget.attrs.update({
            'class': 'h-5 w-5 text-[#800505] focus:ring-[#800505] border-gray-300 rounded'
        })



class FacultyCreationForm(forms.Form):
    faculty_code = forms.CharField(
        max_length=20,
        required=False,
        help_text="Unique faculty code, e.g. FA0014SP2021"
    )

    first_name = forms.CharField(
        max_length=100,
        validators=[name_part_validator],
        label="First Name",
    )
    middle_name = forms.CharField(
        max_length=100,
        required=False,
        validators=[name_part_validator],
        label="Middle Name",
    )
    last_name = forms.CharField(
        max_length=100,
        validators=[name_part_validator],
        label="Last Name",
    )
    suffix = forms.CharField(
        max_length=20,
        required=False,
        validators=[name_part_validator],
        label="Suffix (optional)",
    )

    email = forms.EmailField()
    birth_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"})
    )
    contact_number = forms.CharField(max_length=14, required=False, label="Contact Number")
    status = forms.ModelChoiceField(
        queryset=EmploymentStatus.objects.filter(is_active=True),
        required=False
    )
    position = forms.CharField(
        max_length=255,
        required=False,
        label="Position",
        help_text="e.g. Instructor II, Assistant Professor I",
    )
    designation = forms.CharField(
        max_length=255,
        required=False,
        label="Designation",
        help_text="Optional administrative title (e.g. Program Chair).",
    )
    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
        help_text="Secondary email for notifications (optional).",
    )
    password = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.PasswordInput,
        help_text="Leave blank to auto-generate.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {field_class}".strip()
            field.widget.attrs["placeholder"] = field.label

        self.fields["contact_number"].widget.attrs.update({
            "inputmode": "numeric",
            "maxlength": "14",
            "autocomplete": "off",
            "oninput": "formatPhoneInput(this)",
            "placeholder": "e.g. 09171234567",
        })

    def clean_email(self):
        email = self.cleaned_data["email"]
        if Account.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_faculty_code(self):
        code = self.cleaned_data.get("faculty_code")
        if not code:
            return code  # optional for now
        if FacultyProfile.objects.filter(faculty_code=code).exists():
            raise forms.ValidationError("This faculty code is already in use.")
        return code

    def clean_contact_number(self):
        return _normalize_ph_mobile(self.cleaned_data.get("contact_number") or "")

    def generate_random_password(self):
        return "".join(
            secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            for _ in range(8)
        )



class FacultyPublicSignupForm(forms.Form):
    """
    Public self-signup form for faculty. Creates inactive accounts pending admin approval.
    Mirrors FacultyCreationForm structure for consistency.
    """
    first_name = forms.CharField(
        max_length=100,
        validators=[name_part_validator],
        label="First Name",
    )
    middle_name = forms.CharField(
        max_length=100,
        required=False,
        validators=[name_part_validator],
        label="Middle Name",
    )
    last_name = forms.CharField(
        max_length=100,
        validators=[name_part_validator],
        label="Last Name",
    )
    suffix = forms.CharField(
        max_length=20,
        required=False,
        validators=[name_part_validator],
        label="Suffix",
    )

    email = forms.EmailField(
        label="PUP WebMail",
        help_text="Will be used for account login and notifications. Must be a valid PUP email.",
        )
    faculty_code = forms.CharField(
        max_length=20,
        required=True,
        label="Faculty Code",
        help_text="e.g., FA0018SP2023",
    )
    status = forms.ModelChoiceField(
        queryset=EmploymentStatus.objects.filter(is_active=True),
        required=True,
        label="Employment Status",
    )
    contact_number = forms.CharField(
        max_length=14,
        required=False,
        label="Contact Number",
        help_text="Enter 11-digit PH mobile number (e.g. 09171234567)",
    )
    birth_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Birth Date",
    )
    position = forms.CharField(
        max_length=255,
        required=False,
        label="Position",
        help_text="e.g. Instructor II, Assistant Professor I",
    )
    designation = forms.CharField(
        max_length=255,
        required=False,
        label="Designation",
        help_text="Optional administrative title (e.g. Academic Head, Program Chair).",
    )
    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
        help_text="Optional secondary email for notifications.",
    )

    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Password",
        help_text="Use at least 8 characters.",
    )
    confirm_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Confirm Password",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {field_class}".strip()
            field.widget.attrs["placeholder"] = field.label

        self.fields["middle_name"].widget.attrs["placeholder"] = "Middle Name (Optional)"
        self.fields["suffix"].widget.attrs["placeholder"] = "Suffix (Optional)"
        self.fields["password"].widget.attrs["class"] = f"{self.fields['password'].widget.attrs.get('class', '')} pr-12".strip()
        self.fields["confirm_password"].widget.attrs["class"] = f"{self.fields['confirm_password'].widget.attrs.get('class', '')} pr-12".strip()
        self.fields["contact_number"].widget.attrs.update({
            "inputmode": "numeric",
            "maxlength": "14",
            "autocomplete": "off",
            "oninput": "formatPhoneInput(this)",
            "placeholder": "e.g. 09171234567",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Account.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_contact_number(self):
        return _normalize_ph_mobile(self.cleaned_data.get("contact_number") or "")

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data



class FacultyEditForm(forms.ModelForm):
    email = forms.EmailField(
        label='Email',
        max_length=255,
        widget=forms.EmailInput()
    )
    contact_number = forms.CharField(
        max_length=14,
        required=False,
        label="Contact Number",
    )

    class Meta:
        model = FacultyProfile
        fields = ['faculty_code', 'name', 'position', 'designation', 'personal_email', 'birth_date', 'contact_number', 'status']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        account_instance = kwargs.pop('account_instance', None)
        super().__init__(*args, **kwargs)
        self.fields['status'].queryset = EmploymentStatus.objects.filter(is_active=True)
        if account_instance:
            self.fields['email'].initial = account_instance.email

        common_class = 'w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505] transition'

        self.fields['email'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Email',
        })
        self.fields['faculty_code'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Faculty Code',
        })
        self.fields['name'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Full Name',
        })
        self.fields['position'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Position (e.g. Instructor II)',
        })
        self.fields['designation'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Designation (e.g. Program Chair)',
        })
        self.fields['personal_email'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Personal Email (optional)',
        })
        self.fields['birth_date'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Birth Date',
        })
        self.fields['contact_number'].widget.attrs.update({
            'class': common_class,
            'placeholder': 'Contact Number',
            'inputmode': 'numeric',
            'maxlength': '14',
            'autocomplete': 'off',
            'oninput': 'formatPhoneInput(this)',
        })
        self.fields['status'].widget.attrs.update({
            'class': common_class,
        })

    def clean_contact_number(self):
        return _normalize_ph_mobile(self.cleaned_data.get("contact_number") or "")

    def save(self, commit=True):
        faculty_profile = super().save(commit=False)
        if commit:
            faculty_profile.save()
        return faculty_profile



class FacultyDocumentUploadForm(forms.Form):
    document_category = forms.ModelChoiceField(
        queryset=DocumentCategory.objects.none(),  
        required=True,
        label="Category",
        empty_label="Select a Category",
    )
    document_name = forms.CharField(
        max_length=255,
        required=True,
        label="Document Name",
    )
    file = forms.FileField(
        required=True,
        label="File",
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Expiry Date",
    )

    def __init__(self, *args, **kwargs):
        index = kwargs.pop("index", None)
        self.faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)

        self.fields['document_category'].queryset = (
            DocumentCategory.objects
            .filter(deliverables__isnull=True)
            .order_by('name')
        )

        input_class = (
            'w-full border border-gray-300 rounded-lg px-2 py-2 text-sm '
            'focus:outline-none focus:ring-2 focus:ring-[#800505]'
        )

        self.fields['document_category'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Category',
        })
        self.fields['document_name'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Document Name',
        })

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
        """
        - Completely empty row is allowed and ignored.
        - If any field is filled, require category, name, file,
          and expiry_date if category.requires_expiry_date.
        - Validate extension against category.allowed_file_types.
        """
        cleaned_data = super().clean()
        category = cleaned_data.get("document_category")
        name = cleaned_data.get("document_name")
        file = cleaned_data.get("file")
        expiry = cleaned_data.get("expiry_date")

        row_is_empty = not category and not name and not file and not expiry

        if row_is_empty:
            for field in ["document_category", "document_name", "file", "expiry_date"]:
                if field in self._errors:
                    del self._errors[field]
            return cleaned_data

        errors = {}

        if not category:
            errors["document_category"] = "Please select a category."
        if not name:
            errors["document_name"] = "Please enter the document name."
        if not file:
            errors["file"] = "Please choose a file to upload."

        if category:
            if category.requires_expiry_date and not expiry:
                errors["expiry_date"] = "Expiry date is required for this document category."

            if file:
                ext = os.path.splitext(file.name)[1].lower().lstrip('.')
                allowed = category.allowed_file_types.values_list("extension", flat=True)
                if ext not in allowed:
                    errors["file"] = f"File type '.{ext}' is not allowed for {category.name}."

        if errors:
            raise ValidationError(errors)

        return cleaned_data



class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            'title', 'content', 'scheduled_publish_at', 'is_important',
            'send_email', 'attachment_link', 'end_date',
        ]
        widgets = {
            'scheduled_publish_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs["class"] = field_class
                field.widget.attrs["placeholder"] = field.label
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "rounded text-[#800505] focus:ring-[#800505]"
        if "scheduled_publish_at" in self.fields:
            self.fields["scheduled_publish_at"].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_scheduled_publish_at(self):
        scheduled_publish_at = self.cleaned_data.get('scheduled_publish_at')
        if scheduled_publish_at and scheduled_publish_at <= timezone.now():
            raise ValidationError("Scheduled publish date and time must be in the future.")
        return scheduled_publish_at



class AssignDeliverablesForm(forms.Form):
    semester = forms.ModelChoiceField(queryset=Semester.objects.all())
    enable_auto_assign = forms.BooleanField(required=False, initial=True, label="Enable Auto-Assign")
    template = forms.ModelChoiceField(queryset=DeliverableTemplate.objects.all(), required=False)
    deadline = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "rounded text-[#800505] focus:ring-[#800505]"
            elif fname == "deadline":
                field.widget.attrs["class"] = field_class
                field.widget.attrs["placeholder"] = field.label
            else:
                field.widget.attrs["class"] = field_class
                field.widget.attrs["placeholder"] = field.label

    def clean(self):
        cleaned_data = super().clean()
        enable_auto_assign = cleaned_data.get("enable_auto_assign")
        template = cleaned_data.get("template")
        deadline = cleaned_data.get("deadline")

        if not enable_auto_assign:
            if template is None:
                self.add_error("template", "Template is required when auto-assign is disabled.")
            if deadline is None:
                self.add_error("deadline", "Deadline is required when auto-assign is disabled.")

        return cleaned_data








CURRENT_YEAR = datetime.datetime.now().year
YEAR_CHOICES = [(y, f"{y}–{y + 1}") for y in range(CURRENT_YEAR, CURRENT_YEAR + 8)]


class AcademicYearForm(forms.ModelForm):
    academic_year = forms.ChoiceField(
        choices=YEAR_CHOICES,
        label="Academic Year",
        widget=forms.Select(attrs={
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505] transition'
        })
    )

    class Meta:
        model = AcademicYear
        fields = ['is_active']
        labels = {
            'is_active': 'Active'
        }
        widgets = {
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-[#800505] focus:ring-[#800505] transition'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'academic_year':
                if isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs.update({
                        'class': 'form-checkbox h-5 w-5 text-[#800505] focus:ring-[#800505] transition'
                    })
                else:
                    field.widget.attrs.update({
                        'class': 'w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505] transition'
                    })

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
        academic_year_value = cleaned_data.get('academic_year')
        if academic_year_value is None:
            return cleaned_data 

        year_start = int(academic_year_value)
        if AcademicYear.objects.filter(year_start=year_start, year_end=year_start + 1).exists():
            raise forms.ValidationError("This academic year already exists.")
        return cleaned_data


class SemesterForm(forms.ModelForm):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505] transition'
        }),
        required=True
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505] transition'
        }),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        filtered_choices = [choice for choice in Semester.SEMESTER_CHOICES if choice[0] != "full"]
        self.fields["semester_type"].choices = filtered_choices

    class Meta:
        model = Semester
        fields = ['semester_type', 'start_date', 'end_date']
        widgets = {
            'semester_type': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#800505] transition'
            })
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")

        if start and end and start > end:
            raise forms.ValidationError("Start date cannot be after end date.")

        return cleaned_data


class BaseSemesterFormSet(BaseModelFormSet):
    """
    Enforces:
    - Exactly three semesters: 1st, 2nd, summer
    - No duplicate semester_type
    - Non-overlapping semesters in order: 1st -> 2nd -> summer
    """
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        semesters = []
        present_types = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE", False):
                continue

            sem_type = form.cleaned_data.get("semester_type")
            start = form.cleaned_data.get("start_date")
            end = form.cleaned_data.get("end_date")

            if not sem_type or not start or not end:
                continue

            semesters.append((sem_type, start, end, form))
            present_types.add(sem_type)

        # 1) Exactly the three required types
        required_types = {"1st", "2nd", "summer"}
        if present_types != required_types:
            missing = required_types - present_types
            extra = present_types - required_types
            msg_parts = []
            if missing:
                msg_parts.append(f"Missing semesters: {', '.join(sorted(missing))}.")
            if extra:
                msg_parts.append(f"Unexpected semester types: {', '.join(sorted(extra))}.")
            raise ValidationError(" ".join(msg_parts) or "Invalid semester configuration.")

        # 2) No duplicates
        type_to_form = {}
        for sem_type, start, end, form in semesters:
            if sem_type in type_to_form:
                form.add_error("semester_type", "Duplicate semester type for this academic year.")
            else:
                type_to_form[sem_type] = form

        if any(form.errors for _, _, _, form in semesters):
            return

        # 3) Non-overlapping & ordered: 1st -> 2nd -> summer
        order = {"1st": 1, "2nd": 2, "summer": 3}
        semesters_sorted = sorted(semesters, key=lambda s: order[s[0]])

        for idx, (sem_type, start, end, form) in enumerate(semesters_sorted):
            if idx > 0:
                prev_type, prev_start, prev_end, prev_form = semesters_sorted[idx - 1]

                # must not overlap and must be chronological
                if prev_end > start:
                    form.add_error(
                        "start_date",
                        f"{sem_type} semester must start on or after the end of {prev_type} semester."
                    )
                    prev_form.add_error(
                        "end_date",
                        f"{prev_type} semester must end on or before the start of {sem_type} semester."
                    )



class DeliverableTemplateForm(forms.ModelForm):
    document_categories = forms.ModelMultipleChoiceField(
        queryset=DocumentCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Required Documents"
    )

    is_default = forms.BooleanField(
            required=False,
            label="Default",
            widget=forms.CheckboxInput(attrs={
                "class": "h-4 w-4 text-[#800505] rounded focus:ring-[#800505]"
    })
        )
    class Meta:
        model = DeliverableTemplate
        fields = ['name', 'is_default', 'document_categories']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                if isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs["class"] = "rounded text-[#800505] focus:ring-[#800505]"
                else:
                    field.widget.attrs["class"] = field_class
                    field.widget.attrs["placeholder"] = field.label
        # Add custom class to checklist for template targeting (optional)
        if "document_categories" in self.fields:
            self.fields["document_categories"].widget.attrs["class"] = "custom-checklist"


class IndexedFormSet(BaseFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.index = index 

    def _construct_form(self, i, **kwargs):
        kwargs['index'] = i
        return super()._construct_form(i, **kwargs)





class FacultyDeliverableUploadForm(forms.Form):
    teaching_assignment = forms.ModelChoiceField(
        queryset=TeachingAssignment.objects.none(),
        required=False,
        label="Teaching Assignment",
        empty_label="Select Subject / Section",
    )
    deliverable = forms.ModelChoiceField(
        queryset=Deliverable.objects.none(),
        required=False,
        label="Deliverable",
        empty_label="Select Deliverable",
    )
    file = forms.FileField(
        required=False,
        label="File",
    )

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop("faculty", None)
        index = kwargs.pop("index", None)
        request = kwargs.pop("request", None) 
        super().__init__(*args, **kwargs)

        # Keep for clean() checks
        self.faculty = faculty

        # Styling
        base_select_classes = (
            "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505]"
        )

        self.fields["teaching_assignment"].widget.attrs.update({
            "class": base_select_classes,
        })
        self.fields["deliverable"].widget.attrs.update({
            "class": base_select_classes,
        })

        file_id = f"file_input_{index}" if index is not None else "file_input__empty"
        self.fields["file"].widget.attrs.update({
            "class": "hidden",
            "id": file_id,
        })

        # IMPORTANT: custom label just for this form (no model change)
        self.fields["teaching_assignment"].label_from_instance = (
            lambda obj: f"{obj.subject_code} – {obj.subject_description} ({obj.year_section})"
        )

        # Defaults from query params (only for first form on GET)
        ta_prefill = None
        deliverable_prefill = None
        if request is not None and index == 0 and request.method == "GET":
            ta_id = request.GET.get("ta")
            deliverable_id = request.GET.get("deliverable")
            if ta_id and ta_id.isdigit():
                ta_prefill = int(ta_id)
            if deliverable_id and deliverable_id.isdigit():
                deliverable_prefill = int(deliverable_id)

        # Default: empty deliverables until TA is selected
        self.fields["deliverable"].queryset = Deliverable.objects.none()

        if not faculty:
            self.fields["teaching_assignment"].queryset = TeachingAssignment.objects.none()
            return

        active_semester = Semester.objects.filter(is_active=True).first()
        self.active_semester = active_semester  # stash for clean()

        if not active_semester:
            self.fields["teaching_assignment"].queryset = TeachingAssignment.objects.none()
            return

        # Teaching assignments for active semester
        ta_qs = TeachingAssignment.objects.filter(
            faculty=faculty,
            semester=active_semester
        ).order_by("subject_code", "year_section")
        self.fields["teaching_assignment"].queryset = ta_qs

        # Determine current TA:
        # 1) if bound (POST), use the bound value
        # 2) else, if GET prefill provided, use that
        ta_obj = None

        ta_value = self.data.get(self.add_prefix("teaching_assignment")) if self.is_bound else None
        if ta_value:
            try:
                ta_obj = ta_qs.get(pk=ta_value)
            except (TeachingAssignment.DoesNotExist, ValueError, TypeError):
                ta_obj = None
        elif ta_prefill:
            try:
                ta_obj = ta_qs.get(pk=ta_prefill)
                self.fields["teaching_assignment"].initial = ta_obj
            except TeachingAssignment.DoesNotExist:
                ta_obj = None

        # Only if we have a TA selected, populate deliverables
        if ta_obj:
            base_deliverables_qs = Deliverable.objects.filter(
                semester=active_semester
            ).select_related("document_category")

            # Exclude deliverables already APPROVED for this faculty + TA + semester
            approved_ids = FacultyDocument.objects.filter(
                faculty=faculty,
                semester=active_semester,
                teaching_assignment=ta_obj,
                status="Approved",
            ).values_list("deliverable_id", flat=True)

            d_qs = base_deliverables_qs.exclude(id__in=approved_ids)
            self.fields["deliverable"].queryset = d_qs.order_by("document_category__name")

            # Pre-select deliverable if passed via GET and still valid
            if deliverable_prefill and not self.is_bound:
                try:
                    d_obj = self.fields["deliverable"].queryset.get(pk=deliverable_prefill)
                    self.fields["deliverable"].initial = d_obj
                except Deliverable.DoesNotExist:
                    pass

    def clean(self):
        """
        Enforce:
          - A completely empty row is allowed and ignored.
          - If any field in the row is filled, all three are required.
          - Block upload if there is already an APPROVED document (scoped to faculty + active semester).
          - Validate file extension against deliverable.document_category.allowed_file_types.
        """
        cleaned = super().clean()
        teaching_assignment = cleaned.get("teaching_assignment")
        deliverable = cleaned.get("deliverable")
        file = cleaned.get("file")

        row_is_empty = not teaching_assignment and not deliverable and not file
        if row_is_empty:
            return cleaned

        # Require all if any is provided
        if not teaching_assignment:
            self.add_error("teaching_assignment", "Please select a teaching assignment.")
        if not deliverable:
            self.add_error("deliverable", "Please select a deliverable.")
        if not file:
            self.add_error("file", "Please choose a file to upload.")

        # If required checks already failed, stop early
        if self.errors:
            raise ValidationError("Please correct the errors below.")

        # Safety: ensure we can scope checks properly
        active_semester = getattr(self, "active_semester", None)
        if not active_semester:
            raise ValidationError("No active semester is set. Please contact the administrator.")
        if not self.faculty:
            raise ValidationError("Only faculty can upload deliverables.")

        # Block if already approved for this faculty + semester + TA + deliverable
        exists_approved = FacultyDocument.objects.filter(
            faculty=self.faculty,
            semester=active_semester,
            teaching_assignment=teaching_assignment,
            deliverable=deliverable,
            status="Approved",
        ).exists()
        if exists_approved:
            raise ValidationError(
                "This deliverable is already approved for this teaching assignment. "
                "You can no longer upload a new version."
            )

        if deliverable.deadline and timezone.localdate() > deliverable.deadline:
            raise ValidationError(
                f"Upload is blocked. The deadline for {deliverable.document_category.name} "
                f"was {deliverable.deadline.strftime('%b %d, %Y')}."
            )

        # File type validation based on deliverable's document category
        category = deliverable.document_category  # non-null per your model

        ext = os.path.splitext(file.name)[1].lower().lstrip(".")  # e.g. ".PDF" -> "pdf"
        allowed = set(category.allowed_file_types.values_list("extension", flat=True))
        allowed = {e.strip().lower().lstrip(".") for e in allowed}

        if not allowed:
            self.add_error("file", f"No allowed file types are configured for {category.name}.")
            raise ValidationError("Please correct the errors below.")

        if ext not in allowed:
            self.add_error(
                "file",
                f"File type '.{ext}' is not allowed for {category.name}. "
                f"Allowed: {', '.join(sorted(allowed))}."
            )
            raise ValidationError("Please correct the errors below.")


        return cleaned





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




class ApplicantLoginForm(forms.Form):
    applicant_id = forms.CharField(max_length=20)
    email = forms.EmailField()

class ApplicantForm(forms.ModelForm):
    area_of_specialization = forms.ModelChoiceField(
        queryset=AreaOfSpecialization.objects.filter(is_active=True).order_by('name'),
        required=True,
        label="Area of Specialization",
        empty_label="Select your area of specialization",
    )
    contact_number = forms.CharField(
        max_length=14,
        required=False,
        label="Contact Number",
    )
    emergency_contact_number = forms.CharField(
        max_length=14, 
        required=False,
        label="Emergency Contact Number",
    )

    class Meta:
        model = Applicant
        fields = [
            # Basic info
            "first_name",
            "middle_name",
            "last_name",
            "suffix",
            "email",
            "contact_number",
            "area_of_specialization",
            "birth_date",
            "facebook_link",
            "emergency_contact_name",
            "emergency_contact_number",
            # Educational background
            "college_degree",
            "college_institution",
            "masters_degree",
            "masters_institution",
            "doctorate_degree",
            "doctorate_institution",
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'facebook_link': forms.TextInput(attrs={
                'placeholder': 'https://facebook.com/yourprofile',
            }),
        }
        labels = {
            'facebook_link': "Facebook Profile Link",
            'college_degree': "College Degree",
            'college_institution': "College Educational Institution",
            'masters_degree': "Master's Degree",
            'masters_institution': "Master's Educational Institution",
            'doctorate_degree': "Doctorate Degree",
            'doctorate_institution': "Doctorate Educational Institution",
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

        self.fields['contact_number'].widget.attrs.update({
            "placeholder": "e.g. 09171234567",
            "maxlength": "14",
            "inputmode": "numeric",
            "autocomplete": "off",
            "oninput": "formatPhoneInput(this)",
        })
        self.fields['emergency_contact_number'].widget.attrs.update({
            "placeholder": "e.g. 09171234567",
            "maxlength": "14",
            "inputmode": "numeric",
            "autocomplete": "off",
            "oninput": "formatPhoneInput(this)",
        })
        self.fields['middle_name'].required = False
        self.fields['suffix'].required = False
        self.fields['facebook_link'].required = False
        # Educational background fields are optional
        for fname in ('college_degree', 'college_institution', 'masters_degree',
                      'masters_institution', 'doctorate_degree', 'doctorate_institution'):
            self.fields[fname].required = False

    def clean_contact_number(self):
        return _normalize_ph_mobile(self.cleaned_data.get("contact_number") or "")

    def clean_emergency_contact_number(self):
        return _normalize_ph_mobile(self.cleaned_data.get("emergency_contact_number") or "")







class ApplicantEducationForm(forms.ModelForm):
    class Meta:
        model = Applicant
        fields = [
            'college_degree', 'college_institution',
            'masters_degree', 'masters_institution',
            'doctorate_degree', 'doctorate_institution',
        ]
        labels = {
            'college_degree': 'College Degree',
            'college_institution': 'College Institution',
            'masters_degree': "Master's Degree",
            'masters_institution': "Master's Institution",
            'doctorate_degree': 'Doctorate Degree',
            'doctorate_institution': 'Doctorate Institution',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for field in self.fields.values():
            field.required = False
            field.widget.attrs['class'] = field_class


MAX_FILE_SIZE = 15 * 1024 * 1024
ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
]


class ApplicantDocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ApplicantDocument
        fields = ["document_category", "file", "expiry_date", "remarks"]

    def __init__(self, *args, required_doc_cats=None, fixed_document_category=None, index=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_document_category = fixed_document_category
        self._index = index  # store for potential debugging

        # If a specific category is fixed for this form
        if self.fixed_document_category:
            # We don't want users to pick the category; it's fixed
            self.fields.pop("document_category", None)
            self.instance.document_category = self.fixed_document_category
            doc_cat = self.fixed_document_category
        else:
            doc_cat = self.initial.get("document_category")
            if required_doc_cats is not None and "document_category" in self.fields:
                self.fields["document_category"].queryset = required_doc_cats

        # If this category requires an expiry date, make field required
        if doc_cat and getattr(doc_cat, "requires_expiry_date", False):
            self.fields["expiry_date"].required = True

        # If category is required, make file required at the form level
        self.fields["file"].required = False 
        
        # Hide file input, assign unique id for JS/label targeting
        file_id = f'file_input_{index}' if index is not None else 'file_input__empty'
        existing_class = self.fields["file"].widget.attrs.get("class", "")
        self.fields["file"].widget.attrs.update(
            {
                "class": (existing_class + " hidden").strip(),
                "id": file_id,
                "placeholder": "Select File",
            }
        )

    # Per-field validation for file
    def clean_file(self):
        f = self.cleaned_data.get("file")
        doc_cat = self.fixed_document_category or getattr(self.instance, "document_category", None)

        # Required file check
        if doc_cat and getattr(doc_cat, "is_required", False) and not f:
            raise forms.ValidationError("This document is required.")

        # If optional and not provided, that's fine
        if not f:
            return f

        # Size validation
        if f.size > MAX_FILE_SIZE:
            raise forms.ValidationError("File size must be 15MB or less.")

        # Content type validation (optional but recommended)
        if hasattr(f, "content_type") and f.content_type not in ALLOWED_CONTENT_TYPES:
            raise forms.ValidationError("Invalid file type. Please upload a PDF or image file.")

        return f

    def clean_expiry_date(self):
        expiry = self.cleaned_data.get("expiry_date")
        doc_cat = self.fixed_document_category or getattr(self.instance, "document_category", None)

        if doc_cat and getattr(doc_cat, "requires_expiry_date", False) and not expiry:
            raise forms.ValidationError("Expiry date is required for this document type.")

        return expiry



class ApplicantRequiredDocumentForm(forms.ModelForm):
    class Meta:
        model = ApplicantRequiredDocument
        fields = ["document_category", "is_required", "validity_days"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for name, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label

        self.fields["validity_days"].required = False

        # Optional: when creating a new record, only show categories that
        # don't already have ApplicantRequiredDocument
        if not self.instance.pk:
            used_ids = ApplicantRequiredDocument.objects.values_list(
                "document_category_id", flat=True
            )
            self.fields["document_category"].queryset = DocumentCategory.objects.exclude(
                id__in=used_ids
            )

    def clean(self):
        cleaned_data = super().clean()
        doc_cat = cleaned_data.get("document_category")

        # Extra safety on uniqueness (in case of race conditions)
        if doc_cat:
            qs = ApplicantRequiredDocument.objects.filter(document_category=doc_cat)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "This document category already has a required document configuration."
                )

        return cleaned_data






CONFLICT_MESSAGE = (
    "This time range overlaps another assignment for this faculty on this day in this semester."
)

class TeachingAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeachingAssignment
        fields = [
            'subject_code', 'subject_description', 'year_section',
            'day_of_week', 'start_time', 'end_time', 'room', 'semester'
        ]
        widgets = {
            'start_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
            'end_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)

        # Base classes
        for name, field in self.fields.items():
            base = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (
                base + ' block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm '
                'focus:outline-none focus:ring-2 focus:ring-[#800505] focus:border-[#800505] text-sm'
            ).strip()

        if 'room' in self.fields:
            self.fields['room'].widget.attrs.setdefault('placeholder', 'e.g. LAB-3 or RM 201')

    def clean(self):
        cleaned = super().clean()

        # Ensure faculty is attached early
        if self.faculty and not self.instance.faculty_id:
            self.instance.faculty = self.faculty

        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        day = cleaned.get('day_of_week')
        semester = cleaned.get('semester')
        faculty = self.instance.faculty

        # Time ordering
        if start and end and start >= end:
            self.add_error('end_time', "End time must be after start time.")

        # Overlap check only if all pieces valid so far
        if faculty and semester and day and start and end:
            qs = TeachingAssignment.objects.filter(
                faculty=faculty,
                semester=semester,
                day_of_week=day,
                start_time__lt=end,
                end_time__gt=start
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                self.add_error('start_time', CONFLICT_MESSAGE)
                self.add_error('end_time', CONFLICT_MESSAGE)
                # Or self.add_error(None, CONFLICT_MESSAGE) for a top-only message

        return cleaned

    def full_clean(self):
        """
        Override to append error styling classes automatically after validation.
        """
        super().full_clean()
        if self.errors:
            for field_name in self.errors:
                if field_name in self.fields:
                    cls = self.fields[field_name].widget.attrs.get('class', '')
                    if 'border-red-500' not in cls:
                        self.fields[field_name].widget.attrs['class'] = (
                            cls + ' border-red-500 focus:border-red-600 focus:ring-red-600'
                        ).strip()
class TeachingAssignmentBulkUploadForm(forms.Form):
    file = forms.FileField(help_text="Upload CSV or Excel file")






class ManualAttendanceLogForm(forms.ModelForm):
    faculty = forms.ModelChoiceField(queryset=FacultyProfile.objects.all(), widget=forms.HiddenInput())
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}))
    teaching_assignments = forms.ModelMultipleChoiceField(
        queryset=TeachingAssignment.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-input', 'size': 5}),
        required=False,
        help_text="Select one or more teaching assignments."
    )
    time_in = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}))
    time_out = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}))

    class Meta:
        model = AttendanceLog
        fields = ['faculty', 'date', 'teaching_assignments']  # DO NOT include time_in/time_out

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)
        if faculty:
            self.fields['teaching_assignments'].queryset = TeachingAssignment.objects.filter(faculty=faculty)
        else:
            self.fields['teaching_assignments'].queryset = TeachingAssignment.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        faculty = cleaned_data.get("faculty")
        date = cleaned_data.get("date")
        teaching_assignments = cleaned_data.get("teaching_assignments")
        time_in = cleaned_data.get("time_in")
        time_out = cleaned_data.get("time_out")

        # Only one log per faculty per date allowed
        exists = AttendanceLog.objects.filter(faculty=faculty, date=date)
        if self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise forms.ValidationError("An attendance log for this faculty and date already exists.")

        if teaching_assignments and len(teaching_assignments) > 0:
            start_times = [ta.start_time for ta in teaching_assignments]
            end_times = [ta.end_time for ta in teaching_assignments]
            assignment_time_in = min(start_times)
            assignment_time_out = max(end_times)
            if time_in != assignment_time_in or time_out != assignment_time_out:
                raise forms.ValidationError("Time in/out must match selected assignments.")
        else:
            if time_in and time_out and time_out <= time_in:
                raise forms.ValidationError("Time out must be after time in.")
        return cleaned_data





class DTRLogEditForm(forms.ModelForm):
    time_in = forms.DateTimeField(
        required=True,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Time In"
    )
    time_out = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Time Out"
    )

    class Meta:
        model = AttendanceLog
        fields = ['time_in', 'time_out']

    def clean(self):
        cleaned = super().clean()
        time_in = cleaned.get('time_in')
        time_out = cleaned.get('time_out')

        # End time must be after start time (allow time_out blank)
        if time_in and time_out and time_out <= time_in:
            self.add_error('time_out', "Time Out must be after Time In.")

        if time_in:
            faculty = self.instance.faculty
            date = time_in.date()
            qs = AttendanceLog.objects.filter(faculty=faculty, date=date)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("There is already an attendance log for this faculty on this date.")

        return cleaned



class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class TeachingAssignmentBulkUploadForm(forms.Form):
    files = forms.FileField(
        label="Select one or more files to upload",
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
        }),
        help_text=(
            "Upload one or more CSV or Excel files (.csv, .xls, .xlsx). "
            "Required columns (case-insensitive): "
            "'Subject Code', 'Subject Description', 'Year/Section', 'Room', 'Day of Week', "
            "'Start Time', 'End Time', 'Semester'. Optional column: 'Faculty Name' "
            "(used to preselect a faculty on the preview page). "
            "Time formats accepted: 24-hour (e.g. 08:00) "
            "(e.g. 10:00 AM). For Excel files times may be Excel time values. "
            "Semester may be provided as:"
            "  • a numeric Semester id (preferred), or"
            "  • a text value describing semester_type and academic year, e.g. '1st 2025-2026' or '1st Semester 2025–2026'."
            "Room may be free text (e.g. 'LAB-3', 'RM 201')."

        )
    )

    def clean_files(self):
        files = self.files.getlist('files') if hasattr(self, 'files') else None
        if not files:
            raise forms.ValidationError("Please select at least one file.")
        return files
    


class PUPSiteForm(forms.ModelForm):
    class Meta:
        model = PUPSite
        fields = ["name", "url", "description", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    "class": "h-5 w-5 text-[#800505] focus:ring-[#800505] border-gray-300 rounded"
                })
            else:
                field.widget.attrs.update({
                    "class": base_class,
                    "placeholder": field.label,
                })



class BackgroundUploadForm(forms.Form):
    file = forms.ImageField(
        label="Background image (JPG/PNG/WebP)",
        required=False,
        help_text="Upload to replace the current landing background image.",
    )
    use_background_image = forms.BooleanField(
        required=False,
        label="Use background image",
        initial=True,
    )

    overlay_style = forms.ChoiceField(
        label="Background overlay style",
        choices=LandingAppearance.OVERLAY_CHOICES,
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure file input id for custom button
        self.fields["file"].widget.attrs.update({
            "id": "bg_file_input",
        })

        appearance = LandingAppearance.get_solo()
        self.fields["use_background_image"].initial = appearance.use_background_image
        self.fields["overlay_style"].initial = appearance.overlay_style

    def clean_file(self):
        img = self.cleaned_data.get("file")
        if not img:
            return img
        max_size = 5 * 1024 * 1024  # 5 MB
        if img.size > max_size:
            raise forms.ValidationError("Image file too large (max 5MB).")
        if img.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("Please upload a JPG, PNG, or WebP image.")
        return img
    


class DocumentTemplateForm(forms.Form):
    document_category = forms.ModelChoiceField(
        queryset=DocumentCategory.objects.all().order_by("name"),
        required=True,
        label="Document Category",
        help_text="Each category may only have one template."
    )
    name = forms.CharField(
        max_length=255,
        required=True,
        label="Template Name",
    )
    file = forms.FileField(
        required=True,
        label="Template File",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        input_class = (
            'w-full border border-gray-300 rounded-lg px-2 py-2 text-sm '
            'focus:outline-none focus:ring-2 focus:ring-[#800505]'
        )

        self.fields['document_category'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Category',
        })
        self.fields['name'].widget.attrs.update({
            'class': input_class,
            'placeholder': 'Template Name',
        })
        self.fields['file'].widget.attrs.update({
            'class': 'hidden',
            'id': 'id_file',
        })

    def clean_document_category(self):
        from adminhub.models import DocumentTemplate
        category = self.cleaned_data["document_category"]

        existing = (
            DocumentTemplate.objects
            .filter(document_category=category)
            .first()
        )

        if existing:
            raise forms.ValidationError(
                f"This category already has a template: '{existing.name}'. "
                "Delete it first if you want to replace it."
            )
        return category
    


class DocumentCategoryForm(forms.ModelForm):
    """Form for creating and updating Document Categories."""
    allowed_file_types = forms.ModelMultipleChoiceField(
        queryset=FileType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Allowed File Types",
        help_text="Select all file types that are allowed for this category.",
    )

    class Meta:
        model = DocumentCategory
        fields = [
            "name",
            "description",
            "is_required",
            "requires_expiry_date",
            "allowed_file_types",
        ]



class EmploymentStatusForm(forms.ModelForm):
    class Meta:
        model = EmploymentStatus
        fields = ["name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-[#800505] "
            "focus:outline-none text-sm"
        )
        for name, field in self.fields.items():
            field.widget.attrs["class"] = field_class
            field.widget.attrs["placeholder"] = field.label

