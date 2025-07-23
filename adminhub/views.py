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



# Create your views here.

@admin_required
def home(request):
    data = get_admin_data(request)
    return render(request, 'admin/admin_home.html', data)

    

@admin_required
def documents(request):
    search_query = request.GET.get('q', '')
    category_id = request.GET.get('category')
    status_filter = request.GET.get('status')

    # Queryset: All documents
    documents = FacultyDocument.objects.select_related('faculty__account', 'document_category')

    # Apply search filters
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

    categories = DocumentCategory.objects.all().order_by('name')

    context = {
        'documents': documents.order_by('-uploaded_at'),
        'categories': categories,
        'search_query': search_query,
        'selected_category': category_id,
        'selected_status': status_filter,
    }

    return render (request, 'admin/admin_documents_storage.html', context)


@admin_required
def faculty_list_view(request):
    faculty_data = get_all_faculty_data()
    return render(request, 'admin/admin_faculty_list.html', faculty_data)

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

    context = {
        'faculty': faculty,
        'documents': documents,
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
