from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.http import FileResponse
import os

def serve_sw(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'sw.js')
    return FileResponse(open(sw_path, 'rb'), content_type='application/javascript')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sw.js', serve_sw, name='sw'),
    path('', include('core.urls')),
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)