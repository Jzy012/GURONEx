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
    


from django.contrib.auth.forms import PasswordChangeForm

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
        # Style the checkbox with Tailwind classes for a modern look
        self.fields['two_factor_authentication'].widget.attrs.update({
            'class': 'h-5 w-5 text-[#800505] focus:ring-[#800505] border-gray-300 rounded'
        })




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
from django.core.exceptions import ValidationError
from faculty.models import DocumentCategory
import os

class FacultyDocumentUploadForm(forms.Form):
    document_category = forms.ModelChoiceField(
        queryset=DocumentCategory.objects.none(),  # set in __init__
        required=True,
        label="Category",
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

        # EXCLUDE all categories that are used in ANY Deliverable
        # i.e. document upload is only for non-deliverable categories
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
            # Clear default 'required' errors so empty rows are truly ignored
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
            # Expiry requirement
            if category.requires_expiry_date and not expiry:
                errors["expiry_date"] = "Expiry date is required for this document category."

            # File extension validation
            if file:
                ext = os.path.splitext(file.name)[1].lower().lstrip('.')
                allowed = category.allowed_file_types.values_list("extension", flat=True)
                if ext not in allowed:
                    errors["file"] = f"File type '.{ext}' is not allowed for {category.name}."

        if errors:
            raise ValidationError(errors)

        return cleaned_data





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
    deadline = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = (
            "w-full border border-gray-300 rounded-lg px-4 py-1.5 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#800505] transition"
        )
        for fname, field in self.fields.items():
            if fname == "deadline":
                # Ensure the date input gets the same styling
                field.widget.attrs["class"] = field_class
                field.widget.attrs["placeholder"] = field.label
            else:
                field.widget.attrs["class"] = field_class
                field.widget.attrs["placeholder"] = field.label





from django import forms
from django.forms import BaseModelFormSet
from django.core.exceptions import ValidationError
from faculty.models import AcademicYear, Semester
import datetime


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
            return cleaned_data  # field-level errors will handle this

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
        # Exclude "full" option
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
            # field-level errors already present
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
                # Required field errors already handled on form level
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
        # Add custom class to checklist for template targeting (optional)
        if "document_categories" in self.fields:
            self.fields["document_categories"].widget.attrs["class"] = "custom-checklist"

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

from django import forms
from faculty.models import FacultyDocument, Deliverable, Semester, TeachingAssignment
from django.utils import timezone

from django import forms
from faculty.models import FacultyDocument, Deliverable, Semester, TeachingAssignment


from django import forms
from faculty.models import FacultyDocument, Deliverable, Semester, TeachingAssignment
    

class FacultyDeliverableUploadForm(forms.Form):
    teaching_assignment = forms.ModelChoiceField(
        queryset=TeachingAssignment.objects.none(),
        label="Teaching Assignment",
        empty_label="Select Subject / Section",
    )
    deliverable = forms.ModelChoiceField(
        queryset=Deliverable.objects.none(),
        label="Deliverable",
        empty_label="Select Deliverable",
    )
    file = forms.FileField(label="File")

    def __init__(self, *args, **kwargs):
        faculty = kwargs.pop("faculty", None)
        index = kwargs.pop('index', None)
        request = kwargs.pop('request', None)  # to read ?ta=&deliverable=
        super().__init__(*args, **kwargs)

        # Styling
        base_select_classes = (
            'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm '
            'focus:outline-none focus:ring-2 focus:ring-[#800505]'
        )

        self.fields['teaching_assignment'].widget.attrs.update({
            'class': base_select_classes,
        })
        self.fields['deliverable'].widget.attrs.update({
            'class': base_select_classes,
        })

        file_id = f'file_input_{index}' if index is not None else 'file_input__empty'
        self.fields['file'].widget.attrs.update({
            'class': 'hidden',
            'id': file_id,
        })

        # IMPORTANT: custom label just for this form (no model change)
        self.fields['teaching_assignment'].label_from_instance = (
            lambda obj: f"{obj.subject_code} – {obj.subject_description} ({obj.year_section})"
        )

        # Defaults from query params (only for first form on GET)
        ta_prefill = None
        deliverable_prefill = None
        if request is not None and index == 0 and request.method == "GET":
            ta_id = request.GET.get('ta')
            deliverable_id = request.GET.get('deliverable')
            if ta_id and ta_id.isdigit():
                ta_prefill = int(ta_id)
            if deliverable_id and deliverable_id.isdigit():
                deliverable_prefill = int(deliverable_id)

        self.fields['deliverable'].queryset = Deliverable.objects.none()  # default: empty

        if faculty:
            active_semester = Semester.objects.filter(is_active=True).first()
            if active_semester:
                # Teaching assignments for active semester
                ta_qs = TeachingAssignment.objects.filter(
                    faculty=faculty,
                    semester=active_semester
                ).order_by('subject_code', 'year_section')
                self.fields['teaching_assignment'].queryset = ta_qs

                # Determine current TA:
                # 1) if bound (POST), use the bound value
                # 2) else, if GET prefill provided, use that
                ta_obj = None

                ta_value = self.data.get(self.add_prefix('teaching_assignment')) if self.is_bound else None
                if ta_value:
                    try:
                        ta_obj = ta_qs.get(pk=ta_value)
                    except (TeachingAssignment.DoesNotExist, ValueError):
                        ta_obj = None
                elif ta_prefill:
                    try:
                        ta_obj = ta_qs.get(pk=ta_prefill)
                        self.fields['teaching_assignment'].initial = ta_obj
                    except TeachingAssignment.DoesNotExist:
                        ta_obj = None

                # Only if we have a TA selected, populate deliverables
                if ta_obj:
                    base_deliverables_qs = Deliverable.objects.filter(
                        semester=active_semester
                    ).select_related('document_category')

                    # Exclude deliverables already APPROVED for this TA
                    approved_ids = FacultyDocument.objects.filter(
                        faculty=faculty,
                        semester=active_semester,
                        teaching_assignment=ta_obj,
                        status='Approved'
                    ).values_list('deliverable_id', flat=True)

                    d_qs = base_deliverables_qs.exclude(id__in=approved_ids)
                    self.fields['deliverable'].queryset = d_qs.order_by('document_category__name')

                    # Pre-select deliverable if passed via GET and still valid
                    if deliverable_prefill and not self.is_bound:
                        try:
                            d_obj = self.fields['deliverable'].queryset.get(pk=deliverable_prefill)
                            self.fields['deliverable'].initial = d_obj
                        except Deliverable.DoesNotExist:
                            pass
            else:
                self.fields['teaching_assignment'].queryset = TeachingAssignment.objects.none()
                # deliverables already set to none above

    def clean(self):
        """
        Enforce:
          - A completely empty row is allowed and ignored.
          - If any field in the row is filled, all three are required.
          - Block upload if there is already an APPROVED document.
        """
        cleaned = super().clean()
        teaching_assignment = cleaned.get("teaching_assignment")
        deliverable = cleaned.get("deliverable")
        file = cleaned.get("file")

        # Check if the row is completely empty
        row_is_empty = not teaching_assignment and not deliverable and not file

        # If the row is fully empty, we treat it as optional and don't raise errors here
        if row_is_empty:
            # Remove any field errors that might have been added by default 'required' validation
            for field in ["teaching_assignment", "deliverable", "file"]:
                if field in self._errors:
                    del self._errors[field]
            return cleaned

        # If we reach here, it means at least one of the fields has a value,
        # so we require ALL of them to be present.
        errors = {}
        if not teaching_assignment:
            errors["teaching_assignment"] = "Please select a teaching assignment."
        if not deliverable:
            errors["deliverable"] = "Please select a deliverable."
        if not file:
            errors["file"] = "Please choose a file to upload."

        if errors:
            # Raise field-specific errors
            raise ValidationError(errors)

        # Existing approval check (keep your logic)
        if deliverable and teaching_assignment:
            exists_approved = FacultyDocument.objects.filter(
                deliverable=deliverable,
                teaching_assignment=teaching_assignment,
                status='Approved'
            ).exists()

            if exists_approved:
                raise ValidationError(
                    "This deliverable is already approved for this teaching assignment. "
                    "You can no longer upload a new version."
                )

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



from django import forms
from applicant.models import Applicant
# import other forms you already have in this file as needed


class ApplicantForm(forms.ModelForm):
    class Meta:
        model = Applicant
        fields = [
            # Basic info
            "first_name",
            "middle_name",               # NEW
            "last_name",
            "suffix",
            "email",
            "contact_number",
            "department",
            "birth_date",

            # Educational background
            "college_course",
            "college_school_name",
            "college_graduation_year",
            "grad_course",
            "grad_school_name",
            "grad_graduation_year",

            # Emergency contact
            "emergency_contact_name",
            "emergency_contact_number",
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

        # Optional / helpful placeholders
        self.fields['contact_number'].widget.attrs["placeholder"] = "e.g. 09XXXXXXXXX"
        self.fields['middle_name'].required = False
        self.fields['grad_course'].required = False
        self.fields['grad_school_name'].required = False
        self.fields['grad_graduation_year'].required = False

  


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




from django import forms
from rfid.models import AttendanceLog, FacultyProfile
from django.core.exceptions import ValidationError


from django import forms
from rfid.models import AttendanceLog
from faculty.models import FacultyProfile, TeachingAssignment

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





from django import forms
from rfid.models import AttendanceLog

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

        # Only one log per faculty per day allowed (except this instance)
        if time_in:
            faculty = self.instance.faculty
            date = time_in.date()
            qs = AttendanceLog.objects.filter(faculty=faculty, date=date)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("There is already an attendance log for this faculty on this date.")

        return cleaned

from django import forms


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
        # When using multiple files the view should call request.FILES.getlist('files').
        files = self.files.getlist('files') if hasattr(self, 'files') else None
        if not files:
            raise forms.ValidationError("Please select at least one file.")
        return files
    






from django import forms
from adminhub.models import PUPSite



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





from django import forms


from django import forms
from base.models import LandingAppearance


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
    







# adminhub/forms.py
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
        # Hide the file field itself; we trigger it by label click
        self.fields['file'].widget.attrs.update({
            'class': 'hidden',
            'id': 'id_file',
        })

    def clean_document_category(self):
        from adminhub.models import DocumentTemplate
        category = self.cleaned_data["document_category"]
        existing = getattr(category, "document_template", None)
        if existing:
            raise forms.ValidationError(
                f"This category already has a template: '{existing.name}'. "
                "Delete it first if you want to replace it."
            )
        return category