from django.shortcuts import render, redirect, get_object_or_404
from base.decorators import admin_required, faculty_required
from base.forms import TwoFactorToggleForm
from django.contrib import messages
from base.utils.admin_data import get_admin_data, get_all_faculty_data



from django.shortcuts import render
from django.db.models import Q
from faculty.models import FacultyDocument, DocumentCategory
from faculty.models import FacultyProfile

# Create Faculty View
from django.contrib import messages
from base.models import Account
from base.forms import FacultyCreationForm
from services.google_drive_service import CentralGoogleDriveService
from django.db import transaction
from django.contrib.auth.decorators import login_required

from django.core.paginator import Paginator


# Create your views here.

@admin_required
def home(request):
    data = get_admin_data(request)
    return render(request, 'admin/admin_home.html', data)

    

from django.db.models import Count, Sum, Q
from django.utils.functional import cached_property

@admin_required
def documents(request):
    search_query = request.GET.get('q', '')
    category_id = request.GET.get('category')
    status_filter = request.GET.get('status')

    documents = FacultyDocument.objects.select_related('faculty__account', 'document_category')

    if search_query:
        documents = documents.filter(
            Q(document_name__icontains=search_query) |
            Q(faculty__account__first_name__icontains=search_query) |
            Q(faculty__account__last_name__icontains=search_query) |
            Q(faculty__account__email__icontains=search_query)
        )

    if category_id:
        documents = documents.filter(document_category_id=category_id)

    if status_filter:
        documents = documents.filter(status=status_filter)

    documents = documents.order_by('-uploaded_at')

    # 📊 Stats
    total_documents = documents.count()
    total_storage_bytes = documents.aggregate(total_size=Sum('file_size'))['total_size'] or 0
    pending_documents = documents.filter(status='Pending').count()

    def format_storage(size_bytes):
        if size_bytes >= 1024**3:
            return f"{size_bytes / (1024**3):.2f} GB"
        elif size_bytes >= 1024**2:
            return f"{size_bytes / (1024**2):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes} bytes"

    total_storage_human = format_storage(total_storage_bytes)

    # 📊 Per-category breakdown
    categories = (
        DocumentCategory.objects
        .annotate(
            total_docs=Count('documents'),
            total_storage_bytes=Sum('documents__file_size'),
            pending_count=Count('documents', filter=Q(documents__status='Pending'))
        )
        .order_by('name')
    )

    # Convert storage to human-readable format
    for cat in categories:
        cat.total_storage = format_storage(cat.total_storage_bytes or 0)

    # Convert each document's file size to human-readable format
    for doc in documents:
        doc.size_human = format_storage(doc.file_size or 0)


    # Pagination
    paginator = Paginator(documents, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        'page_obj': page_obj,
        'paginator': paginator,
        'categories': categories,
        'search_query': search_query,
        'selected_category': category_id,
        'selected_status': status_filter,

        # 📊 Stats
        'total_documents': total_documents,
        'total_storage': total_storage_human,
        'pending_documents': pending_documents,

        'querystring': querystring,
    }

    return render(request, 'admin/admin_documents_storage.html', context)




from django.shortcuts import render
from django.db.models import Count, Q
from django.core.paginator import Paginator
from faculty.models import FacultyProfile, EmploymentStatus, FacultyDocument

@admin_required
def faculty_list_view(request):
    search = request.GET.get('search', '')
    status_id = request.GET.get('status', '')

    faculty_qs = FacultyProfile.objects.all().select_related('status').order_by('name')
    if search:
        faculty_qs = faculty_qs.filter(name__icontains=search)
    if status_id:
        faculty_qs = faculty_qs.filter(status_id=status_id)

    # Annotate with pending document counts
    faculty_qs = faculty_qs.annotate(
        pending_documents=Count('documents', filter=Q(documents__status='Pending'))
    )

    total_faculty = FacultyProfile.objects.count()
    total_pending_docs = FacultyDocument.objects.filter(status='Pending').count()
    statuses = EmploymentStatus.objects.filter(is_active=True)

    # Pagination (same as in documents view)
    paginator = Paginator(faculty_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Preserve other GET params for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    return render(request, 'admin/admin_faculty_list.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'statuses': statuses,
        'total_faculty': total_faculty,
        'total_pending_docs': total_pending_docs,
        'search': search,
        'status_id': status_id,
        'querystring': querystring,
    })




@admin_required
def admin_settings(request):
    return render(request, 'admin/admin_settings.html') 


@admin_required
def admin_2fa(request):
    user = request.user

    if request.method == 'POST':
        form = TwoFactorToggleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "2FA setting updated.")
            return redirect("adminhub:admin_2fa")
    else:
        form = TwoFactorToggleForm(instance=user)

    return render(request, "admin/admin_2fa.html", {"form": form})




@admin_required
def faculty_detail_view(request, faculty_uuid):
    faculty = get_object_or_404(
        FacultyProfile.objects.select_related('account', 'status'),
        uuid=faculty_uuid
    )

    # Fetch related documents (optional: order/filter as needed)
    documents = faculty.documents.all().order_by('-uploaded_at')

    # Instantiate the form with the faculty instance and account_instance
    form = FacultyEditForm(instance=faculty, account_instance=faculty.account)

    context = {
        'faculty': faculty,
        'documents': documents,
        'form': form,  # <-- pass form to context!
    }

    return render(request, 'admin/admin_faculty_detail.html', context)





@admin_required
def create_faculty_view(request):
    if request.method == "POST":
        form = FacultyCreationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            password = data['password'] or form.generate_random_password()

            try:
                with transaction.atomic():
                    # 1. Create account
                    account = Account.objects.create_user(
                        email=data['email'],
                        password=password,
                        role='faculty'
                    )

                    # 2. Create faculty profile
                    faculty = FacultyProfile.objects.create(
                        account=account,
                        name=data['name'],
                        department=data['department'],
                        birth_date=data['birth_date'],
                        contact_number=data['contact_number'],
                        status=data['status'],
                    )

                    # 3. Attempt to create Drive folder
                    try:
                        drive = CentralGoogleDriveService()
                        folder_id = drive.create_faculty_folder(faculty)
                        faculty.gdrive_folder_id = folder_id
                        faculty.save()
                        messages.success(request, f"✅ Faculty created. Folder ID: {folder_id}")
                    except Exception as e:
                        messages.warning(request, f"⚠️ Faculty saved but Drive folder creation failed: {str(e)}")

                    # Optional: show password if auto-generated
                    if not data['password']:
                        messages.info(request, f"🛡️ Auto-generated password: {password}")

                    return redirect('adminhub:faculty_list')

            except Exception as e:
                messages.error(request, f"❌ Error: {str(e)}")
    else:
        form = FacultyCreationForm()

    return render(request, 'admin/admin_faculty_creation.html', {'form': form})



from base.forms import FacultyEditForm


@admin_required
def edit_faculty_view(request, faculty_uuid):
    faculty = get_object_or_404(FacultyProfile, uuid=faculty_uuid)
    account = faculty.account

    if request.method == "POST":
        form = FacultyEditForm(request.POST, instance=faculty, account_instance=account)
        if form.is_valid():
            email = form.cleaned_data['email']

            # Check email uniqueness for other accounts
            if Account.objects.filter(email=email).exclude(pk=account.pk).exists():
                form.add_error('email', "This email is already in use.")
            else:
                form.save()
                account.email = email
                account.save()
                messages.success(request, "✅ Faculty details updated successfully.")
                return redirect('adminhub:faculty_detail', faculty_uuid=faculty.uuid)
    else:
        form = FacultyEditForm(instance=faculty, account_instance=account)
    
    
    return render(request, 'admin/admin_faculty_edit.html', {'form': form, 'faculty': faculty})

#Announcements View



from datetime import date
from django.shortcuts import render
from django.contrib import messages

@admin_required
def announcements_view(request):
    today = date.today()
    announcements = Announcement.objects.order_by('-created_at')

    return render(request, 'admin/admin_announcements.html', {
        'announcements': announcements,
        'today': today
    })




from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from base.forms import AnnouncementForm
from .models import Announcement
from base.models import Account  # adjust as needed

@admin_required
def create_announcement_view(request):
    if request.user.role != 'admin':
        messages.error(request, "You are not authorized to create announcements.")
        return redirect('admin_home')  # or any fallback route

    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.creator = request.user
            announcement.visible_to_roles = form.cleaned_data['visible_to_roles']
            announcement.save()
            messages.success(request, "Announcement posted successfully.")

            # (Optional) Handle email sending later

            return redirect('adminhub:announcements')  # you’ll create this soon
        else:
            messages.error(request, "There was an error in your submission.")
    else:
        form = AnnouncementForm()

    return render(request, 'admin/admin_create_announcement.html', {'form': form})




from django.shortcuts import get_object_or_404

@admin_required
def edit_announcement_view(request, uuid):
    announcement = get_object_or_404(Announcement, uuid=uuid)

    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.visible_to_roles = form.cleaned_data['visible_to_roles']
            updated.save()
            messages.success(request, "Announcement updated successfully.")
            return redirect('adminhub:announcements')
    else:
        form = AnnouncementForm(instance=announcement)
        # Convert JSON list back to choices
        form.fields['visible_to_roles'].initial = announcement.visible_to_roles

    return render(request, 'admin/admin_edit_announcement.html', {'form': form, 'announcement': announcement})





from django.shortcuts import get_object_or_404, redirect

@admin_required
def delete_announcement_view(request, uuid):
    announcement = get_object_or_404(Announcement, uuid=uuid)
    announcement.delete()
    messages.success(request, f"'{announcement.title}' has been permanently deleted.")
    return redirect('adminhub:announcements')






# views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from base.forms import AssignDeliverablesForm
from faculty.models import Deliverable, DeliverableTemplate
from django.utils import timezone


from django.db.models import Q
from faculty.models import FacultyProfile, FacultyDocument, Deliverable, Semester

from django.utils import timezone
from faculty.models import FacultyProfile, FacultyDocument, Deliverable, Semester

from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from faculty.models import FacultyProfile, FacultyDocument, Deliverable, Semester

@admin_required
def deliverables_view(request):
    today = timezone.now().date()
    semester = Semester.objects.filter(is_active=True, start_date__lte=today, end_date__gte=today).select_related('academic_year').first()
    total_faculty = FacultyProfile.objects.count()

    completed_submissions = 0
    pending_submissions = 0
    deliverables_list = []
    academic_year_str = ""
    semester_str = ""

    # --- Search, filter, and pagination params ---
    search = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    page_number = request.GET.get("page")
    page_size = 10  # You can adjust this

    faculty_statuses_raw = []

    if semester:
        academic_year = semester.academic_year
        academic_year_str = str(academic_year)
        semester_str = semester.get_semester_type_display()

        deliverables = Deliverable.objects.filter(semester=semester).select_related('document_category')
        deliverable_ids = list(deliverables.values_list('id', flat=True))
        deliverable_count = len(deliverable_ids)
        deliverables_list = [
            {
                "name": d.document_category.name,
                "deadline": d.deadline,
            } for d in deliverables
        ]

        faculty_qs = FacultyProfile.objects.select_related('account').all()
        if search:
            faculty_qs = faculty_qs.filter(
                Q(name__icontains=search) | Q(account__email__icontains=search)
            )

        for faculty in faculty_qs:
            approved_count = 0
            for d_id in deliverable_ids:
                doc = FacultyDocument.objects.filter(
                    faculty=faculty,
                    semester=semester,
                    deliverable_id=d_id,
                    status="Approved"
                ).first()
                if doc:
                    approved_count += 1

            faculty_status = {
                "name": faculty.name,
                "email": faculty.account.email,
                "approved_count": approved_count,
                "total_required": deliverable_count,
                "faculty_uuid": faculty.uuid,
            }

            # Filter by status if specified
            if status_filter == "completed" and (approved_count != deliverable_count or deliverable_count == 0):
                continue
            if status_filter == "pending" and (approved_count == deliverable_count and deliverable_count > 0):
                continue

            faculty_statuses_raw.append(faculty_status)

    # Pagination of faculty_statuses_raw
    paginator = Paginator(faculty_statuses_raw, page_size)
    page_obj = paginator.get_page(page_number)

    # Recompute completed/pending based on the unpaginated filtered queryset
    completed_submissions = sum(
        1 for f in faculty_statuses_raw if f["approved_count"] == f["total_required"] and f["total_required"] > 0
    )
    pending_submissions = len(faculty_statuses_raw) - completed_submissions

    # Preserve other GET params for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    context = {
        'total_faculty': total_faculty,
        'completed_submissions': completed_submissions,
        'pending_submissions': pending_submissions,
        'page_obj': page_obj,
        'paginator': paginator,
        'deliverables_list': deliverables_list,
        'academic_year_str': academic_year_str,
        'semester_str': semester_str,
        'search': search,
        'status_filter': status_filter,
        'querystring': querystring,
    }
    return render(request, 'admin/admin_deliverables.html', context)


@admin_required
def assign_deliverables_view(request):
    if request.method == 'POST':
        form = AssignDeliverablesForm(request.POST)
        if form.is_valid():
            semester = form.cleaned_data['semester']
            template = form.cleaned_data['template']
            deadline = form.cleaned_data['deadline']

            count = 0
            for doc_category in template.document_categories.all():
                if not Deliverable.objects.filter(
                    semester=semester,
                    document_category=doc_category
                ).exists():
                    Deliverable.objects.create(
                        semester=semester,
                        document_category=doc_category,
                        deadline=deadline
                    )
                    count += 1

            messages.success(request, f"{count} deliverables assigned to {semester}.")
            return redirect('adminhub:deliverables')  # Adjust to your dashboard/redirect
    else:
        form = AssignDeliverablesForm()

    return render(request, 'admin/admin_assign_deliverables.html', {'form': form})




from django.contrib import messages
from django.shortcuts import render, redirect
from base.forms import DeliverableTemplateForm


@admin_required
def deliverable_templates_view(request):
    templates = DeliverableTemplate.objects.all()
    return render(request, 'admin/admin_deliverable_templates.html', {'templates': templates})


@admin_required
def create_deliverable_template_view(request):
    if request.method == 'POST':
        form = DeliverableTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Deliverable template created.")
            return redirect('adminhub:deliverable_templates')
    else:
        form = DeliverableTemplateForm()

    return render(request, 'admin/admin_create_deliverable_template.html', {'form': form})




# views.py
from django.forms import modelformset_factory
from base.forms import AcademicYearForm, SemesterForm
from faculty.models import AcademicYear, Semester

@admin_required
def academic_years_view(request):
    academic_years = AcademicYear.objects.all()
    return render(request, 'admin/admin_academic_years.html', {'academic_years': academic_years})




@admin_required
def create_academic_year_view(request):
    SemesterFormSet = modelformset_factory(Semester, form=SemesterForm, extra=3, can_delete=False)

    if request.method == 'POST':
        year_form = AcademicYearForm(request.POST)
        formset = SemesterFormSet(request.POST)

        if year_form.is_valid() and formset.is_valid():
            academic_year = year_form.save()

            # Save all semester forms with this academic_year
            for form in formset:
                semester = form.save(commit=False)
                semester.academic_year = academic_year
                semester.save()

            messages.success(request, "Academic year and semesters created.")
            return redirect('adminhub:create_academic_year')

    else:
        year_form = AcademicYearForm()
        formset = SemesterFormSet(queryset=Semester.objects.none(), initial=[
            {'semester_type': '1st'},
            {'semester_type': '2nd'},
            {'semester_type': 'summer'},
        ])

    return render(request, 'admin/admin_create_academic_year.html', {
        'year_form': year_form,
        'formset': formset,
    })








from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from faculty.models import FacultyRequest, RequestType
from base.forms import RequestTypeForm, FacultyRequestForm, AdminFacultyRequestForm

@admin_required
def admin_request_list_view(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    request_type_id = request.GET.get('request_type', '')

    # Base queryset
    requests_qs = FacultyRequest.objects.select_related("faculty", "request_type").order_by("-created_at")
    
    # Filtering
    if search:
        requests_qs = requests_qs.filter(
            Q(description__icontains=search) |
            Q(request_type__name__icontains=search) |
            Q(faculty__name__icontains=search)
        )
    if status:
        requests_qs = requests_qs.filter(status=status)
    if request_type_id:
        requests_qs = requests_qs.filter(request_type_id=request_type_id)

    # Stats
    total_requests = FacultyRequest.objects.count()
    total_pending = FacultyRequest.objects.filter(status="Pending").count()
    total_approved = FacultyRequest.objects.filter(status="Approved").count()
    total_rejected = FacultyRequest.objects.filter(status="Rejected").count()

    statuses = [
        {'id': 'Pending', 'name': 'Pending'},
        {'id': 'Approved', 'name': 'Approved'},
        {'id': 'Rejected', 'name': 'Rejected'},
    ]

    # For request type filter dropdown
    request_types = RequestType.objects.all()

    return render(request, "admin/admin_request_list.html", {
        "requests": requests_qs,
        "statuses": statuses,
        "request_types": request_types,
        "search": search,
        "status": status,
        "request_type_id": request_type_id,
        "total_requests": total_requests,
        "total_pending": total_pending,
        "total_approved": total_approved,
        "total_rejected": total_rejected,
    })


@admin_required
def admin_request_create_view(request):
    if request.method == "POST":
        form = AdminFacultyRequestForm(request.POST)
        if form.is_valid():
            faculty_request = form.save(commit=False)
            faculty_request.created_by_admin = True
            faculty_request.save()
            messages.success(request, "Request created successfully.")
            return redirect("admin_request_list")
    else:
        form = AdminFacultyRequestForm()

    return render(request, "admin/admin_request_form.html", {"form": form})


from django.views.decorators.http import require_POST

@admin_required
@require_POST
def admin_request_action_view(request, uuid):
    faculty_request = get_object_or_404(FacultyRequest, uuid=uuid)
    action = request.POST.get("action")
    remarks = request.POST.get("remarks", "")

    if action == "approve":
        faculty_request.status = "Approved"
        messages.success(request, "Request approved.")
    elif action == "reject":
        faculty_request.status = "Rejected"
        messages.success(request, "Request rejected.")
    else:
        messages.error(request, "Invalid action.")
        return redirect("admin_request_list")

    faculty_request.remarks = remarks
    faculty_request.save()
    return redirect("adminhub:request_list")




@admin_required
def request_type_list_view(request):
    types = RequestType.objects.all().order_by("name")
    return render(request, "admin/requests/request_type_list.html", {"types": types})


@admin_required
def request_type_create_view(request):
    if request.method == "POST":
        form = RequestTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Request type added successfully.")
            return redirect("request_type_list")
    else:
        form = RequestTypeForm()

    return render(request, "admin/requests/request_type_form.html", {"form": form})


@admin_required
def request_type_edit_view(request, pk):
    req_type = get_object_or_404(RequestType, pk=pk)
    if request.method == "POST":
        form = RequestTypeForm(request.POST, instance=req_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Request type updated successfully.")
            return redirect("request_type_list")
    else:
        form = RequestTypeForm(instance=req_type)

    return render(request, "admin/requests/request_type_form.html", {"form": form})


@admin_required
def request_type_delete_view(request, pk):
    req_type = get_object_or_404(RequestType, pk=pk)
    req_type.delete()
    messages.success(request, "Request type deleted successfully.")
    return redirect("request_type_list")







from django.shortcuts import render
from django.core.paginator import Paginator
from applicant.models import Applicant

from django.db.models import Count, Q


@admin_required
def applicant_list_view(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    # 1. Queryset: Applicant list, filtered by search and status
    applicant_qs = Applicant.objects.all().order_by('-created_at')
    if search:
        applicant_qs = applicant_qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    if status:
        applicant_qs = applicant_qs.filter(status=status)

    # 2. Annotate pending/missing documents (optional, if you want it in list)
    # applicant_qs = applicant_qs.annotate(
    #     pending_documents=Count('documents', filter=Q(documents__status='Pending'))
    # )

    # 3. Stats for dashboard cards
    total_applicants = Applicant.objects.count()
    total_hired = Applicant.objects.filter(status='hired').count()
    total_failed = Applicant.objects.filter(status='failed').count()
    total_pending = Applicant.objects.filter(status='pending').count()

    # 4. Pagination
    paginator = Paginator(applicant_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 5. For status filter dropdown
    status_choices = Applicant._meta.get_field('status').choices

    # 6. Preserve filters for pagination links
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']
    querystring = get_params.urlencode()

    return render(request, 'admin/admin_applicant_list.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'status_choices': status_choices,
        'total_applicants': total_applicants,
        'total_hired': total_hired,
        'total_failed': total_failed,
        'total_pending': total_pending,
        'search': search,
        'status': status,
        'querystring': querystring,
    })




from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from applicant.models import Applicant, ApplicantDocument
from django.db import transaction
from base.utils.email import send_applicant_status_email

# Statuses in order for the stepper visualization
STEPPER_STATUSES = [
    ('pending', "Pending"),
    ('demo_scheduled', "Demo Scheduled"),
    ('for_interview', "For Interview"),
    ('psych_test', "Psych Test"),
    ('hired', "Hired"),
    ('failed', "Failed"),
]

@admin_required
def applicant_detail_view(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)
    documents = ApplicantDocument.objects.filter(applicant=applicant)
    status_choices = Applicant._meta.get_field('status').choices

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status and new_status != applicant.status:
            with transaction.atomic():
                applicant.status = new_status
                applicant.save()
                send_applicant_status_email(applicant, new_status)
                messages.success(request, "Status updated.")
            return redirect('adminhub:applicant_detail', pk=applicant.pk)
        else:
            messages.warning(request, "No status change detected.")

    # For stepper: build steps with current progress
    stepper = []
    found_active = False
    for value, label in STEPPER_STATUSES:
        is_active = (applicant.status == value)
        stepper.append({
            "value": value,
            "label": label,
            "completed": not found_active and not is_active,
            "active": is_active,
        })
        if is_active:
            found_active = True

    return render(request, 'admin/admin_applicant_detail.html', {
        'applicant': applicant,
        'documents': documents,
        'status_choices': status_choices,
        'stepper': stepper,
    })




from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from applicant.models import Applicant, ApplicantDocument
from faculty.models import FacultyProfile, EmploymentStatus, FacultyDocument
from base.models import Account
from .models import CreatedAccountLog
from services.google_drive_service import CentralGoogleDriveService
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings

@admin_required
def account_creation_view(request):
    hired_applicants = Applicant.objects.filter(
        status='hired', account_created=False
    ).order_by('last_name', 'first_name')

    employment_statuses = EmploymentStatus.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected')
        status_id = request.POST.get('employment_status')
        errors = []
        created = []

        if not status_id:
            messages.error(request, "Employment status is required.")
            return redirect('adminhub:account_creation')

        try:
            emp_status = EmploymentStatus.objects.get(pk=status_id)
        except EmploymentStatus.DoesNotExist:
            messages.error(request, "Selected employment status does not exist.")
            return redirect('adminhub:account_creation')

        for applicant_id in selected_ids:
            email = request.POST.get(f'faculty_email_{applicant_id}', '').strip()
            password = request.POST.get(f'faculty_password_{applicant_id}', '').strip()
            if not email:
                errors.append(f"Applicant {applicant_id}: Faculty email is required.")
                continue
            if Account.objects.filter(email=email).exists():
                errors.append(f"{email}: Email already exists.")
                continue
            if not password:
                password = get_random_string(8)
            try:
                with transaction.atomic():
                    applicant = Applicant.objects.get(pk=applicant_id)
                    account = Account.objects.create_user(
                        email=email,
                        password=password,
                        role='faculty'
                    )
                    faculty = FacultyProfile.objects.create(
                        account=account,
                        name=f"{applicant.first_name} {applicant.last_name}",
                        department=getattr(applicant, "department", ""),
                        birth_date=applicant.birth_date,
                        contact_number=applicant.contact_number,
                        status=emp_status,
                    )
                    # Create Drive folder for the faculty
                    try:
                        drive = CentralGoogleDriveService()
                        folder_id = drive.create_faculty_folder(faculty)
                        faculty.gdrive_folder_id = folder_id
                        faculty.save()
                    except Exception as e:
                        errors.append(f"{email}: Drive folder error: {e}")
                    # Copy applicant docs to faculty and Drive
                    for doc in ApplicantDocument.objects.filter(applicant=applicant):
                        doc_name = f"{applicant.first_name} {applicant.last_name}"
                        if applicant.suffix:
                            doc_name += f" {applicant.suffix}"
                        doc_name += f" - {doc.document_category.name}"
                        try:
                            # Copy the file in Google Drive from applicant to faculty folder
                            new_file_id, new_file_link = drive.copy_file_to_folder(
                                doc.google_drive_id,
                                folder_id,
                                new_name=doc_name
                            )
                        except Exception as e:
                            errors.append(f"{email}: Failed to copy file for document '{doc_name}': {e}")
                            continue  # skip this doc but process others
                        FacultyDocument.objects.create(
                            faculty=faculty,
                            document_name=doc_name,
                            document_category=doc.document_category,
                            file_path=new_file_link,
                            google_drive_id=new_file_id,
                            file_size=doc.file_size,
                            expiry_date=doc.expiry_date,
                            status=doc.status,
                            admin_remarks=doc.admin_remarks,
                            # uploaded_by is skipped (nullable)
                        )
                    # Mark applicant as converted
                    applicant.account_created = True
                    applicant.save()
                    # Log created account
                    CreatedAccountLog.objects.create(
                        faculty_email=email,
                        password=password,
                        applicant=applicant,
                        applicant_name=f"{applicant.first_name} {applicant.last_name}",
                        applicant_email=applicant.email,
                        applicant_id_snapshot=applicant.applicant_id
                    )
                    # Email notification to old applicant email
                    send_mail(
                        subject="[FEMS] Your Faculty Account Has Been Created",
                        message=(
                            f"Hello {applicant.first_name},\n\n"
                            f"Your faculty account has been created.\n"
                            f"Login Email: {email}\n"
                            f"Temporary Password: {password}\n\n"
                            "Please log in and change your password immediately. "
                            "If you have any questions, contact the admin.\n\n"
                            "This is an automated message from FEMS."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[applicant.email],
                        fail_silently=True,
                    )
                    created.append(email)
            except Exception as e:
                errors.append(f"{email}: {str(e)}")

        if created:
            messages.success(request, f"✅ Created accounts: {', '.join(created)}")
        if errors:
            for err in errors:
                messages.error(request, f"❌ {err}")
        return redirect('adminhub:account_creation')

    return render(request, 'admin/admin_account_creation.html', {
        'hired_applicants': hired_applicants,
        'employment_statuses': employment_statuses
    })





@admin_required
def created_account_log_view(request):
    logs = CreatedAccountLog.objects.select_related("applicant").order_by("-created_at")
    return render(request, "admin/admin_account_creation_log.html", {
        "logs": logs
    })