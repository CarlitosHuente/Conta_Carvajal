

# COMANDOS PRINCIPALES DEL PROYECTO

1. Para iniciar el servidor de desarrollo (Local):
   python manage.py runserver

2. Para crear las tablas de la Base de Datos desde cero (Instalación limpia):
   python manage.py makemigrations
   python manage.py migrate
   
3. Para crear un usuario administrador (Superusuario para entrar al /admin):
   python manage.py createsuperuser

---------------------------------------------------------
# GESTIÓN DE LA BASE DE DATOS (DATOS COMO ARCHIVO)
---------------------------------------------------------
A diferencia de PHP donde exportas un ".sql", Django recrea las tablas automáticamente con "migrate". 
Para guardar o mover los DATOS (empresas, trabajadores, perfiles) como un archivo, haz lo siguiente:

4. EXPORTAR DATOS (Crear el archivo de respaldo):
   python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 4 > respaldo_db.json
   
   *Esto generará un archivo "respaldo_db.json" con toda tu información lista para viajar con el proyecto.*

5. IMPORTAR DATOS (Instalar los datos en otro servidor o en local):
   python manage.py loaddata respaldo_db.json

---------------------------------------------------------
# PRODUCCIÓN (cPanel)
---------------------------------------------------------
6. Recolectar estáticos (CSS/JS) para que la web se vea bien:
   python manage.py collectstatic --noinput
   
#Actualizar Github
git add .
git commit -m "Primer cambio desde VS Code"
git push origin main
git push --set-upstream origin prueba-cambios //Rama
git push origin main --force

Se modifico y necesita nuevos cambios

Rama Principal

git checkout main

Secundaria

git checkout feature/contacarvajal



# Crear CArpeta Local
En MAC es con python3
python3 -m venv venv

# Activar LocalHost

.\venv\Scripts\activate
mac.  source venv/bin/activate

#Primer Entorno
    pip install -r requirements.txt
    
# Activar por primera vez
python manage.py migrate

# Correr servidor

python manage.py runserver

En produccion se usa:
cd /home/contaca3/repositories/erp_sistema


