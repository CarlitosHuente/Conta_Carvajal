def create_default_superuser(sender, **kwargs):
    """
    Se ejecuta automáticamente después de hacer un 'migrate'.
    Verifica si existe el usuario Carlos, y si no, lo crea.
    """
    from django.contrib.auth.models import User
    
    username = 'Carlos'
    email = 'carloscarvajal2.0@gmail.com'
    password = 'Carvajal.21'
    
    # La condición clave: solo actuar si el usuario NO existe.
    if not User.objects.filter(username=username).exists():
        print(f"\n[+] Creando superusuario por defecto: {username}...")
        user = User.objects.create_superuser(username=username, email=email, password=password)
        
        # Intentamos asignar el rol de admin al PerfilUsuario
        try:
            from .models import PerfilUsuario
            perfil, created = PerfilUsuario.objects.get_or_create(user=user)
            perfil.rol = 'admin'
            perfil.save()
            print(f"[+] Perfil de 'admin' asignado a {username} correctamente.\n")
        except Exception as e:
            print(f"[-] Advertencia: No se pudo asignar el rol de admin al PerfilUsuario: {e}\n")