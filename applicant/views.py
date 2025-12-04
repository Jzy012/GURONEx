from django.shortcuts import render, redirect, get_object_or_404
from django.forms import formset_factory
from django.contrib import messages
from django.db import transaction

from .models import Applicant, ApplicantDocument, ApplicantRequiredDocument, ApplicantTimeline
from base.forms import ApplicantForm
from base.forms import ApplicantDocumentUploadForm
from faculty.models import DocumentCategory
from services.google_drive_service import CentralGoogleDriveService
from googleapiclient.http import MediaIoBaseUpload
from base.utils.email import send_applicant_submission_receipt

import io


def applicant_home(request):
    return render(request, "applicants/applicant_home.html")


def applicant_apply(request):
    required_docs = ApplicantRequiredDocument.objects.all()
    doc_categories = [doc.document_category for doc in required_docs]

    if request.method == "POST":
        basic_form = ApplicantForm(request.POST)
        forms = [
            ApplicantDocumentUploadForm(
                request.POST,
                request.FILES,
                prefix=f"doc{idx}",
                fixed_document_category=doc_cat,
                index=idx
            )
            for idx, doc_cat in enumerate(doc_categories)
        ]
        valid = all(form.is_valid() for form in forms) and basic_form.is_valid()
        if valid:
            with transaction.atomic():
                applicant = basic_form.save()
                drive_service = CentralGoogleDriveService()

                for form, category in zip(forms, doc_categories):
                    file = form.cleaned_data["file"]
                    expiry = form.cleaned_data.get("expiry_date")
                    remarks = form.cleaned_data.get("remarks", "")

                    if file:
                        media = MediaIoBaseUpload(
                            io.BytesIO(file.read()),
                            mimetype=file.content_type,
                            resumable=False
                        )
                        upload = drive_service.service.files().create(
                            body={
                                "name": file.name,
                                "parents": [applicant.google_drive_folder_id],
                            },
                            media_body=media,
                            fields="id,webViewLink"
                        ).execute()

                        ApplicantDocument.objects.create(
                            applicant=applicant,
                            document_category=category,
                            file_path=upload["webViewLink"],
                            google_drive_id=upload["id"],
                            file_size=file.size,
                            expiry_date=expiry,
                            remarks=remarks,
                            status="Pending"
                        )

                ApplicantTimeline.objects.create(
                    applicant=applicant,
                    action="Submitted application",
                    note="Initial application and document upload."
                )

                # Send receipt email (summary + Applicant ID)
                try:
                    send_applicant_submission_receipt(applicant)
                except Exception:
                    # Optionally log this; don't block submission if email fails
                    pass

                messages.success(
                    request,
                    "Application submitted! A copy has been sent to your email. "
                    "Please keep your Applicant ID for future status checks."
                )
                return redirect("applicants:registration_confirmed")
        else:
            messages.error(request, "Please correct errors in your form(s).")
    else:
        basic_form = ApplicantForm()
        forms = [
            ApplicantDocumentUploadForm(
                prefix=f"doc{idx}",
                fixed_document_category=doc_cat,
                index=idx
            )
            for idx, doc_cat in enumerate(doc_categories)
        ]

    context = {
        "basic_form": basic_form,
        "forms": forms,
        "required_docs": required_docs,
    }
    return render(request, "applicants/applicant_apply.html", context)


def applicant_registration_confirmed(request):
    return render(request, "applicants/applicant_registration_confirmed.html")


def applicant_check_status(request):
    if request.method == "POST":
        applicant_id = request.POST.get("applicant_id")
        email = request.POST.get("email")
        try:
            applicant = Applicant.objects.get(applicant_id=applicant_id, email=email)
            return redirect("applicants:status_page", pk=applicant.pk)
        except Applicant.DoesNotExist:
            messages.error(request, "Applicant not found. Please check your ID and email.")
    return render(request, "applicants/applicant_check_status.html")


def applicant_status_page(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)
    docs = applicant.documents.all()
    required_docs = ApplicantRequiredDocument.objects.all()
    timeline = applicant.timeline.order_by("timestamp")

    from adminhub.models import Announcement
    announcements = Announcement.objects.filter(
        visible_to_roles__contains=["applicant"],
        is_active=True
    )

    context = {
        "applicant": applicant,
        "docs": docs,
        "required_docs": required_docs,
        "timeline": timeline,
        "announcements": [a for a in announcements if a.is_visible()],
    }
    return render(request, "applicants/applicant_status_page.html", context)


def applicant_upload_doc(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)

    # Only allow if not hired/failed
    if applicant.status in ["hired", "failed"]:
        messages.error(request, "Cannot upload documents at this stage.")
        return redirect("applicants:status_page", pk=pk)

    required_docs = ApplicantRequiredDocument.objects.all()
    doc_categories = [doc.document_category for doc in required_docs]

    DocumentFormSet = formset_factory(
        ApplicantDocumentUploadForm,
        extra=0,
        max_num=len(doc_categories)
    )

    if request.method == "POST":
        formset = DocumentFormSet(
            request.POST,
            request.FILES,
            form_kwargs={
                "required_doc_cats": DocumentCategory.objects.filter(id__in=[cat.id for cat in doc_categories]),
                "applicant": applicant
            }
        )
        if formset.is_valid():
            drive_service = CentralGoogleDriveService()
            for form in formset:
                if not form.cleaned_data or not form.cleaned_data.get("file"):
                    continue
                file = form.cleaned_data["file"]
                category = form.cleaned_data["document_category"]
                expiry = form.cleaned_data.get("expiry_date")
                remarks = form.cleaned_data.get("remarks", "")

                media = MediaIoBaseUpload(
                    io.BytesIO(file.read()),
                    mimetype=file.content_type,
                    resumable=False
                )
                upload = drive_service.service.files().create(
                    body={
                        "name": file.name,
                        "parents": [applicant.google_drive_folder_id],
                    },
                    media_body=media,
                    fields="id,webViewLink"
                ).execute()

                ApplicantDocument.objects.create(
                    applicant=applicant,
                    document_category=category,
                    file_path=upload["webViewLink"],
                    google_drive_id=upload["id"],
                    file_size=file.size,
                    expiry_date=expiry,
                    remarks=remarks,
                    status="Pending"
                )
                ApplicantTimeline.objects.create(
                    applicant=applicant,
                    action="Uploaded document",
                    note=f"Uploaded document: {category.name}"
                )
            messages.success(request, "Documents uploaded successfully.")
            return redirect("applicants:status_page", pk=pk)
        else:
            messages.error(request, "Please correct errors in your document uploads.")
    else:
        formset = DocumentFormSet(
            form_kwargs={
                "required_doc_cats": DocumentCategory.objects.filter(id__in=[cat.id for cat in doc_categories]),
                "applicant": applicant
            }
        )

    context = {
        "formset": formset,
        "applicant": applicant,
        "required_docs": required_docs,
    }
    return render(request, "applicants/applicant_upload_doc.html", context)