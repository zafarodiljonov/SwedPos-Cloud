from django.contrib import admin, messages

from .models import Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "owners", "key_prefix", "last_sync_at", "last_app_version", "is_active")
    search_fields = ("name", "address", "users__phone", "users__full_name")
    list_filter = ("is_active",)
    fields = ("name", "address", "users", "is_active", "key_prefix", "created_at", "last_sync_at", "last_app_version")
    readonly_fields = ("key_prefix", "created_at", "last_sync_at", "last_app_version")
    filter_horizontal = ("users",)
    actions = ["renew_keys"]

    @admin.display(description="Owners")
    def owners(self, obj):
        return ", ".join(u.full_name or u.phone for u in obj.users.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("users")

    def save_model(self, request, obj, form, change):
        key = None
        if not obj.key_hash:
            key = obj.renew_key()
        super().save_model(request, obj, form, change)
        if key:
            self._show_key(request, obj, key)

    @admin.action(description="Renew sync key (the old key stops working)")
    def renew_keys(self, request, queryset):
        for restaurant in queryset:
            key = restaurant.renew_key()
            restaurant.save()
            self._show_key(request, restaurant, key)

    @staticmethod
    def _show_key(request, restaurant, key):
        messages.warning(request, f"Sync key for “{restaurant}” (shown only now — paste it into SwedPos › Settings › "
                                  f"SwedPos Cloud on the restaurant's server PC): {key}")
