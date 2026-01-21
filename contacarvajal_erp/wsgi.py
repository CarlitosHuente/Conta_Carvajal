import os
from django.core.wsgi import get_wsgi_application

# Apunta a tus settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'contacarvajal_erp.settings')

application = get_wsgi_application()