import os
import sys

# SECCION 1: Ruta al Python de tu entorno virtual en cPanel
INTERP = "/home/contaca3/virtualenv/repositories/erp_sistema/3.12/bin/python"
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# SECCION 2: Configuración estándar
sys.path.insert(0, os.path.dirname(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'contacarvajal_erp.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()