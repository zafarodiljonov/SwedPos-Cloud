from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from .models import normalize_phone


class PhoneLoginForm(AuthenticationForm):
    """Phone number (any common spelling) and password."""

    username = forms.CharField(label=_("web_phone"), max_length=30,
                               widget=forms.TextInput(attrs={"autofocus": True, "inputmode": "tel", "placeholder": "+998 90 123 45 67",
                                                             "autocomplete": "username"}))
    password = forms.CharField(label=_("web_password"), strip=False,
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    error_messages = {
        "invalid_login": _("web_bad_login"),
        "inactive": _("web_bad_login"),
    }

    def clean_username(self):
        return normalize_phone(self.cleaned_data.get("username")) or self.cleaned_data.get("username")
