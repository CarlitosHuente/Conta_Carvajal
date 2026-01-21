import os
import sys

# 1. Agregamos el directorio actual a las rutas de Python
sys.path.insert(0, os.path.dirname(__file__))

# 2. Definimos cuál es el archivo de configuración (settings.py)
# Asegúrate de que 'contacarvajal_erp' sea el nombre real de tu carpeta de configuración
os.environ['DJANGO_SETTINGS_MODULE'] = 'contacarvajal_erp.settings'

# 3. Arrancamos la aplicación Django
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()