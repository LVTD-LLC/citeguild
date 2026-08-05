from allauth.account.forms import LoginForm, SignupForm
from django import forms

from apps.core.models import Profile
from apps.core.utils import DivErrorList


class CustomSignUpForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_class = DivErrorList


class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_class = DivErrorList


class ProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)

    class Meta:
        model = Profile
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save(update_fields=["first_name", "last_name"])
            profile.save()
        return profile


class SiteCreateForm(forms.Form):
    sitemap_url = forms.URLField(
        label="Sitemap URL",
        max_length=2048,
        widget=forms.URLInput(
            attrs={
                "autocomplete": "url",
                "placeholder": "https://example.com/sitemap.xml",
                "class": "app-input mt-1 block w-full",
                "autofocus": True,
            }
        ),
    )


class SiteRenameForm(forms.Form):
    name = forms.CharField(label="Site name", max_length=120, strip=True)


class SitemapUpdateForm(forms.Form):
    name = forms.CharField(
        label="Site name",
        max_length=120,
        strip=True,
        widget=forms.TextInput(
            attrs={"autocomplete": "organization", "class": "app-input mt-1 block w-full"}
        ),
    )
    sitemap_url = forms.URLField(
        label="Sitemap URL",
        max_length=2048,
        widget=forms.URLInput(
            attrs={"autocomplete": "url", "class": "app-input mt-1 block w-full"}
        ),
    )


class SitemapDeleteForm(forms.Form):
    confirmation = forms.CharField(label="Site name", max_length=120, strip=False)

    def __init__(self, *args, project_name: str, **kwargs):
        self.project_name = project_name
        super().__init__(*args, **kwargs)

    def clean_confirmation(self):
        confirmation = self.cleaned_data["confirmation"]
        if confirmation != self.project_name:
            raise forms.ValidationError("Enter the site name exactly to confirm deletion.")
        return confirmation
