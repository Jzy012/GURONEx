from django.shortcuts import render, redirect 
from base.decorators import admin_required, faculty_required


# Create your views here.

@admin_required
def home(request):
    

    return render(request, 'admin_home.html')


@admin_required
def documents(request):
    

    return render (request, 'admin_documents_storage.html')  