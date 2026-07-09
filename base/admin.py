from django.contrib import admin

# Register your models here.


from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.widgets import UnfoldAdminPasswordWidget

from .models import Account  # your custom user model


class AccountCreationForm(forms.ModelForm):
    """Form for creating new users (in admin add user page)"""
    password1 = forms.CharField(label='Password', widget=UnfoldAdminPasswordWidget)
    password2 = forms.CharField(label='Password confirmation', widget=UnfoldAdminPasswordWidget)
    two_factor_authentication = forms.BooleanField(required=False, initial=False)


    class Meta:
        model = Account
        fields = ('email', 'role', 'two_factor_authentication')

    def clean_password2(self):
        # Check if passwords match
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        # Save hashed password
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.two_factor_authentication = self.cleaned_data.get("two_factor_authentication", False)


        # Automatically set is_staff/is_superuser if role == system_admin
        if user.role == 'system_admin':
            user.is_staff = True
            user.is_superuser = True
        else:
            user.is_staff = False
            user.is_superuser = False

        if commit:
            user.save()
        return user

class AccountChangeForm(forms.ModelForm):
    """Form for updating existing users in admin"""
    password = forms.CharField(label='Password', widget=UnfoldAdminPasswordWidget, required=False)

    class Meta:
        model = Account
        fields = ('email', 'role', 'password', 'is_active', 'is_staff', 'is_superuser', 'two_factor_authentication')

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user

class AccountAdmin(BaseUserAdmin, UnfoldModelAdmin):
    """Custom admin class to control admin UI for Accounts"""
    add_form = AccountCreationForm
    form = AccountChangeForm
    model = Account

    list_display = ('email', 'role', 'is_staff', 'is_superuser', 'two_factor_authentication')
    list_filter = ('role', 'is_staff', 'is_superuser', 'two_factor_authentication')

    fieldsets = (
        (None, {'fields': ('email', 'password', 'role', 'two_factor_authentication')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'role', 'password1', 'password2', 'two_factor_authentication'),
        }),
    )
    search_fields = ('email',)
    ordering = ('email',)

admin.site.register(Account, AccountAdmin)




from .models import GoogleStorageAccount

@admin.register(GoogleStorageAccount)
class GoogleStorageAccountAdmin(UnfoldModelAdmin):
    list_display = ("label", "email", "is_active", "token_expiry", "created_at")
    readonly_fields = ("created_at",)
    list_filter = ("is_active",)
