from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('sw.js', RedirectView.as_view(url='/static/js/sw.js'), name='sw'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
