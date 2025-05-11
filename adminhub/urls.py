from django.urls import path
from . import views

app_name = 'adminhub'


urlpatterns = [
    path('admin/home/', views.home, name='home'),

]