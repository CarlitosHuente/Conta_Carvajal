import os
import sys

# RUTA DEL SERVIDOR (Hardcodeada para asegurar que funcione en HostingChile)
# Cuando esto corra en el servidor, usará esta ruta.
sys.path.insert(0, '/home/contaca3/repositories/erp_sistema')

# CONFIGURACIÓN
# Apunta a tu carpeta de configuración (asegúrate que el nombre coincida con tu carpeta real)
os.environ['DJANGO_SETTINGS_MODULE'] = 'contacarvajal_erp.settings'

# ARRANQUE
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()