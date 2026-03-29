from django import forms
from django.core.exceptions import ValidationError
from faculty.models import DocumentCategory
from applicant.models import ApplicantRequiredDocument
import os

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB

class ApplicantRequiredOnlyDocumentUploadForm(forms.Form):
    document_category = forms.ModelChoiceField(
        queryset=DocumentCategory.objects.none(),
        required=True,
        empty_label="Select a Category",
        label="Category",
    )
    file = forms.FileField(required=True, label="File")
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Expiry Date",
    )

    def __init__(self, *args, **kwargs):
        index = kwargs.pop("index", None)
        super().__init__(*args, **kwargs)

        allowed_ids = ApplicantRequiredDocument.objects.values_list("document_category_id", flat=True)
        self.fields["document_category"].queryset = (
            DocumentCategory.objects.filter(id__in=allowed_ids).order_by("name")
        )

        input_class = (
            "w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2.5 pr-9 text-sm "
            "text-gray-800 shadow-sm focus:border-[#800505] focus:ring-1 focus:ring-[#800505] transition"
        )
        self.fields["document_category"].widget.attrs.update({"class": input_class})
        self.fields["expiry_date"].widget.attrs.update({"class": input_class})

        file_id = f"file_input_{index}" if index is not None else "file_input__empty"
        self.fields["file"].widget.attrs.update({"class": "hidden", "id": file_id})

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("document_category")
        file = cleaned.get("file")
        expiry = cleaned.get("expiry_date")

        row_is_empty = not category and not file and not expiry
        if row_is_empty:
            for f in ["document_category", "file", "expiry_date"]:
                if f in self._errors:
                    del self._errors[f]
            return cleaned

        errors = {}
        if not category:
            errors["document_category"] = "Please select a category."
        if not file:
            errors["file"] = "Please choose a file."

        if category:
            # expiry required?
            if category.requires_expiry_date and not expiry:
                errors["expiry_date"] = "Expiry date is required for this document category."

        if file:
            if file.size > MAX_FILE_SIZE:
                errors["file"] = "File size must be 15MB or less."

            if category:
                ext = os.path.splitext(file.name)[1].lower().lstrip(".")
                allowed = set(category.allowed_file_types.values_list("extension", flat=True))
                if allowed and ext not in allowed:
                    errors["file"] = f"File type '.{ext}' is not allowed for {category.name}."

        if errors:
            raise ValidationError(errors)

        return cleaned
