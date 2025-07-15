from django import forms
from .models import Account

class LoginForm(forms.Form):
    email = forms.EmailField(label='Email', max_length=255)
    password = forms.CharField(widget=forms.PasswordInput)



class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(label="Enter your email", max_length=254)


class OTPVerificationForm(forms.Form):
    email = forms.EmailField(label="Email", max_length=254)
    otp = forms.CharField(label="OTP", max_length=6)



class TwoFactorOTPVerificationForm(forms.Form):
    otp = forms.CharField(
        label='Enter OTP',
        max_length=6,
        widget=forms.TextInput(attrs={'placeholder': '6-digit code'})
    )



class PasswordResetForm(forms.Form):
    new_password = forms.CharField(
        label="New password", 
        widget=forms.PasswordInput,
        min_length=8
    )
    confirm_password = forms.CharField(
        label="Confirm new password", 
        widget=forms.PasswordInput,
        min_length=8
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("new_password")
        confirm = cleaned_data.get("confirm_password")
        if password and confirm and password != confirm:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data
    


class TwoFactorToggleForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['two_factor_authentication']
        labels = {
            'two_factor_authentication': 'Enable Two-Factor Authentication (2FA)',
        }
