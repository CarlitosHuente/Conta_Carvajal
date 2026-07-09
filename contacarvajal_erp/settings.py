"""
Django settings for contacarvajal_erp project.
"""

from pathlib import Path
import os
import sys



# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECTOR SEGURIDAD (LOCAL vs PRODUCCIÓN) ---
IN_PRODUCTION = '/home/contaca3' in str(BASE_DIR)

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-iii7&h+qe76kz0ek=i$dii1rf=9p-9o65%1o2d0yxjugv1%-4%')

DEBUG = not IN_PRODUCTION

# IMPORTANTE: En producción, Django es muy estricto con los nombres de dominio.
if IN_PRODUCTION:
    ALLOWED_HOSTS = ['contacarvajal.cl', 'www.contacarvajal.cl']
    # Django 4+: obligatorio para POST/HTTPS detrás del dominio público (evita 403 CSRF).
    CSRF_TRUSTED_ORIGINS = [
        'https://contacarvajal.cl',
        'https://www.contacarvajal.cl',
    ]
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# --- SECTOR ESTÁTICOS (PARA WHITENOISE) ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

if IN_PRODUCTION:
    # Cambiamos a CompressedStaticFilesStorage para evitar el error de manifiesto faltante
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
# --- FIN SECTOR SEGURIDAD ---

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize', # Para formatos de números
    'core.apps.CoreConfig', # Apuntamos a la configuración para que cargue las señales
    'rrhh',
    'contabilidad.apps.ContabilidadConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Recomendado para estáticos en cPanel
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'contacarvajal_erp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'rrhh.context_processors.indicadores_globales',
                'core.context_processors.empresa_context', # <-- AÑADIDO
                'core.context_processors.ui_theme',
            ],
        },
    },
]

WSGI_APPLICATION = 'contacarvajal_erp.wsgi.application'


# --- BASE DE DATOS INTELIGENTE ---
if IN_PRODUCTION:
    # Configuración para HostingChile (cPanel)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': 'contaca3_erp',       # <--- PON AQUÍ EL NOMBRE DE LA BD QUE CREASTE
            'USER': 'contaca3_carvajal',   # <--- PON AQUÍ EL USUARIO QUE CREASTE
            'PASSWORD': 'Carvajal.21',  # <--- PON AQUÍ LA CONTRASEÑA
            'HOST': 'localhost',
            'PORT': '3306',
        }
    }
else:
    # Configuración Local (VS Code)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True
USE_L10N = True


# --- CONCEPTOS VARIABLES (solo cálculo tipo TRAMOS) ---
# En novedades el monto capturado es BRUTO (neto + IVA). La clasificación en tramos usa ese bruto.
# El % del tramo elegido se aplica sobre el NETO entero: round(bruto / (1 + IVA/100)).
# Para cambiar el alícuota sin tocar código: variable de entorno CONCEPTO_VARIABLE_TRAMOS_IVA_PORCIENTO (entero, ej. 19).
CONCEPTO_VARIABLE_TRAMOS_IVA_PORCIENTO = int(
    os.environ.get('CONCEPTO_VARIABLE_TRAMOS_IVA_PORCIENTO', '19')
)


# --- ARCHIVOS ESTÁTICOS (CSS, JS, IMAGES) ---
# --- INICIO SECTOR ESTÁTICOS ---
STATIC_URL = '/static/'

# Carpeta FINAL donde cPanel recolectará todo (Prohibido editar archivos aquí manualmente)
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Carpeta donde TÚ trabajas tus CSS/JS (Aquí sí editas)
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static_local'),
]

# MOTOR DE WHITENOISE (Vital para Producción)
# Esto permite que Django sirva los archivos comprimidos y cacheados eficientemente.
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    
# --- ARCHIVOS MEDIA (LOGOS Y DOCUMENTOS SUBIDOS) ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# --- FIN SECTOR ESTÁTICOS ---

# --- CACHÉ (UF/UTM y datos poco cambiantes) ---
CACHES = {
    'default': {
        'BACKEND': (
            'django.core.cache.backends.filebased.FileBasedCache'
            if IN_PRODUCTION
            else 'django.core.cache.backends.locmem.LocMemCache'
        ),
        'LOCATION': os.path.join(BASE_DIR, '.django_cache'),
        'OPTIONS': {'MAX_ENTRIES': 300},
    }
}

# En producción: priorizar BD local; API solo si INDICADORES_USAR_API=true
INDICADORES_USAR_API = os.environ.get('INDICADORES_USAR_API', 'false').lower() in ('1', 'true', 'yes')
INDICADORES_API_TIMEOUT = float(os.environ.get('INDICADORES_API_TIMEOUT', '1.5'))

# --- UI: tema glass (reversible sin tocar templates) ---
# Desactivar: UI_GLASS_ENABLED=false en entorno, o cambiar a False aquí.
# Sin blur (más rápido): UI_GLASS_BLUR=0 — mantiene transparencias, sin backdrop-filter.
_ui_glass_default = 'false' if IN_PRODUCTION else 'true'
UI_GLASS_ENABLED = os.environ.get('UI_GLASS_ENABLED', _ui_glass_default).lower() in ('1', 'true', 'yes')
UI_GLASS_BLUR = max(0, min(24, int(os.environ.get('UI_GLASS_BLUR', '10'))))

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'core:home'
LOGOUT_REDIRECT_URL = 'login'

# --- SEGURIDAD ---
# Permite que los PDFs se previsualicen en la pantalla dividida (iframes/embeds)
X_FRAME_OPTIONS = 'SAMEORIGIN'