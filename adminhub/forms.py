from django import forms

from faculty.models import FacultyProfile, EmploymentStatus, name_part_validator


def _normalize_ph_mobile(value: str) -> str:
    digits = "".join(filter(str.isdigit, value))
    if len(digits) == 10:
        digits = "0" + digits
    return digits if len(digits) == 11 else value.strip()


class FacultyAdminPendingEditForm(forms.Form):
    """
    Form for editing a pending faculty profile before approval.
    Mirrors FacultyPublicSignupForm field structure but excludes email and password.
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
    faculty_code = forms.CharField(
        max_length=20,
        required=True,
        label="Faculty Code",
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
    )
    designation = forms.CharField(
        max_length=255,
        required=False,
        label="Designation",
    )
    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
    )

    def clean_contact_number(self):
        return _normalize_ph_mobile(self.cleaned_data.get("contact_number") or "")

    def clean_faculty_code(self):
        code = self.cleaned_data.get("faculty_code", "").strip()
        instance_pk = self._instance_pk
        if FacultyProfile.objects.filter(faculty_code=code).exclude(pk=instance_pk).exists():
            raise forms.ValidationError("A faculty profile with this code already exists.")
        return code

    def __init__(self, *args, instance_pk=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._instance_pk = instance_pk
