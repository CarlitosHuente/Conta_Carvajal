from .models import Empresa

def empresa_context(request):
    """
    Hace que la empresa activa en sesión esté disponible en todas las plantillas.
    El objeto estará disponible como `empresa_activa`.
    """
    empresa_activa = None
    empresa_activa_id = request.session.get('empresa_activa_id')

    if empresa_activa_id:
        try:
            empresa_activa = Empresa.objects.get(id=empresa_activa_id)
        except Empresa.DoesNotExist:
            request.session.pop('empresa_activa_id', None)
            
    return {'empresa_activa': empresa_activa}