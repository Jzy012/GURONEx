from django.urls import path
from . import views

app_name = 'faculty'


urlpatterns = [
    path('faculty/home/', views.home, name='home'),

]