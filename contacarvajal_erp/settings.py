"""
Django settings for contacarvajal_erp project.
"""

from pathlib import Path
import os
import sys



# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- CONFIGURACIÓN HÍBRIDA (LOCAL vs PRODUCCIÓN) ---
# Detectamos si estamos en cPanel buscando el usuario 'contaca3' en la ruta
# o si existe una variable de entorno específica.
IN_PRODUCTION = '/home/contaca3' in str(BASE_DIR)

# --- INICIO SECTOR SEGURIDAD ---

# Si no existe (Local), usa la clave insegura por defecto para desarrollo.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-clave-local-desarrollo')

# DEBUG solo será True si NO estamos en producción.
# Puedes forzarlo en cPanel creando la variable DJANGO_DEBUG = 'False'
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True' and not IN_PRODUCTION

ALLOWED_HOSTS = ['contacarvajal.cl', 'www.contacarvajal.cl', 'localhost', '127.0.0.1']
# --- FIN SECTOR SEGURIDAD ---

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rrhh',
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
# --- FIN SECTOR ESTÁTICOS ---