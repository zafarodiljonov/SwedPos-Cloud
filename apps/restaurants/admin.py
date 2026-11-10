from django.contrib import admin, messages

from .models import Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "last_sync_at", "last_app_version", "is_active", "is_demo")
    readonly_fields = ("key_prefix", "created_at", "last_sync_at", "last_app_version")
    filter_horizontal = ("users",)
    actions = ["renew_keys"]

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
