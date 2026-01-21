import os
import sys

# 1. Agregamos la ruta actual al sistema
sys.path.insert(0, os.path.dirname(__file__))

# 2. Apuntamos a tu configuración
os.environ['DJANGO_SETTINGS_MODULE'] = 'contacarvajal_erp.settings'

# 3. Arrancamos la aplicación
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()