from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

@login_required # <--- SECCION: Solo entra si está logueado
def home_redirect_view(request):
    # Si no tiene perfil creado aún (ej: superusuario nuevo), enviarlo al admin
    if not hasattr(request.user, 'perfil'):
        return redirect('/admin/')
    
    # Redirigir según rol
    if request.user.perfil.rol == 'admin':
        return redirect('rrhh:planilla_cobranza') # <--- Cambia esto para ir directo a la tabla # O tu dashboard de contador
    else:
        return redirect('rrhh:home_cliente') # Crearemos esta ruta después