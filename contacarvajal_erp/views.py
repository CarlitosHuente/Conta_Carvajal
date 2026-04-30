from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

@login_required # <--- SECCION: Solo entra si está logueado
def home_redirect_view(request):
    # Si no tiene perfil creado aún (ej: superusuario nuevo), enviarlo al admin
    if not hasattr(request.user, 'perfil'):
        return redirect('/admin/')
    
    # Redirección centralizada al home de core para ambos roles.
    return redirect('core:home')