from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'dhhd',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Use simple storage in dev — no caching, no hashing
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'