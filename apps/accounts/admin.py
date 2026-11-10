from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, min_length=8)

    class Meta:
        model = User
        fields = ("phone", "full_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    ordering = ("phone",)
    list_display = ("phone", "full_name", "is_active", "is_staff", "last_login")
    search_fields = ("phone", "full_name")
    list_filter = ("is_active", "is_staff")
    fieldsets = (
        (None, {"fields": ("phone", "full_name", "password")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "full_name", "password1")}),)
    filter_horizontal = ()
