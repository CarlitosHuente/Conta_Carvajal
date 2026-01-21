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
                'rrhh.context_processors.indicadores_globales',
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
    
# --- ARCHIVOS MEDIA (LOGOS Y DOCUMENTOS SUBIDOS) ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# --- FIN SECTOR ESTÁTICOS ---

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'