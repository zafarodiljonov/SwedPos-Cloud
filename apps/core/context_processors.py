from apps.restaurants.models import Restaurant


def demo(request):
    """The login page offers "Open demo" only when a demo restaurant was loaded (manage.py seed_demo)."""
    return {"demo_available": Restaurant.objects.filter(is_demo=True, is_active=True).exists()}
