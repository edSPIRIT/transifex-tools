"""
Minimal Django settings file for translation validation.
This file is used only for validating PO files using django-admin compilemessages.
"""

# Required Django settings
SECRET_KEY = 'dummy-key-for-translation-validation'
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# Locale settings
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Default language
LANGUAGE_CODE = 'en'

# Available languages
LANGUAGES = [
    ('en', 'English'),
    ('ar', 'Arabic'),
    ('fa', 'Persian'),
    # Add more languages as needed
] 