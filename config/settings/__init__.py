import os
if os.environ.get('DJANGO_SETTINGS_MODULE_ENV') == 'production':
    from .production import *
else:
    from .development import *
