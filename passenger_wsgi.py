import os
import sys

# LÓGICA HÍBRIDA (La Solución Definitiva)
# Si el sistema NO es Windows (o sea, es Linux/cPanel), usa la ruta absoluta.
if sys.platform != 'win32':
    sys.path.insert(0, '/home/contaca3/repositories/erp_sistema')
else:
    # Si estamos en Windows (Tu PC), usa la ruta relativa normal
    sys.path.insert(0, os.path.dirname(__file__))

# Configuración
os.environ['DJANGO_SETTINGS_MODULE'] = 'contacarvajal_erp.settings'

# Arranque
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()