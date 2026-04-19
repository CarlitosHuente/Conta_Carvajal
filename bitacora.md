# Bitácora de Desarrollo - ContaCarvajal ERP

## Estado Actual del Proyecto
* **Entorno Actual:** Desarrollo Local (VS Code, SQLite3, DEBUG=True).
* **Entorno Futuro (Producción):** cPanel (HostingChile), MySQL, servidor WSGI, `whitenoise` para archivos estáticos.
* **Stack Tecnológico:** Django 4.2+, Python 3.12, Bootstrap 5, FontAwesome, PyMuPDF (para lectura de PDFs).

---

## Arquitectura General (Módulos)
El ERP está diseñado de manera modular para escalar sin "código espagueti". Los módulos se activan/desactivan mediante booleanos en el modelo `Empresa`.

1. **`core` (Núcleo):** 
   * Administra el enrutamiento principal (la raíz `/`).
   * Contiene los Modelos Globales (`Empresa`, `PerfilUsuario`).
   * Gestiona el Dashboard Principal y la redirección de inicio de sesión según el rol (`admin` o `cliente`).
2. **`rrhh` (Recursos Humanos):** 
   * Gestión de trabajadores, contratos, liquidaciones de sueldo e indicadores económicos (UF, UTM, etc.).
3. **`contabilidad` (Impuestos y F29):** 
   * Procesamiento de declaraciones del SII, extracción automática de datos y auditoría matemática.

---

## Registro de Cambios y Decisiones Arquitectónicas

### Fecha: 19 de Abril de 2026
**Resumen:** Refactorización del Core y Creación del Módulo de Contabilidad (Lector y Auditor de F29).

#### 1. Refactorización del Núcleo (`core`)
* **Criterio:** La página de inicio y el Dashboard de Administración vivían en `rrhh`. Se movieron a `core` para independizar el sistema. Si un cliente solo contrata Contabilidad, el ERP no debe depender de RRHH para mostrar el inicio.
* **Acción:** Creación de `core/urls.py`, mudanza de vistas de redirección y creación de `core/templates/core/`.

#### 2. Extractor de PDFs Nativos (`contabilidad/extractor.py`)
* **Librería:** Se eligió `PyMuPDF` (`fitz`) por su velocidad y precisión al leer texto en lugar de imágenes (OCR).
* **Criterios de Extracción (Reglas Regex):**
  * Se delimita la zona de lectura buscando etiquetas clave (`[03]`, `[07]`, `[15]`) para RUT, Folio y Período.
  * Los códigos se leen exigiendo que el **Valor** esté al final de la línea (`$`), ignorando números que estén dentro del texto de la Glosa.
  * **Filtro de Ceros:** Cualquier valor `<= 0` se ignora para no ensuciar la base de datos, **EXCEPTO** el Código 91 (Total a Pagar), el cual tiene un rescate de emergencia forzado al final del documento que permite saltos de línea y basura entre medio, ya que es estructuralmente obligatorio.

#### 3. Base de Datos Escalable (`JSONField`)
* **Problema:** El SII cambia, agrega y elimina códigos del F29 constantemente. Crear una columna en la base de datos por cada código requeriría migraciones constantes.
* **Solución:** Se utilizó un `JSONField` (`datos_extraidos`) en el modelo `DeclaracionF29`. Todos los códigos se guardan ahí dinámicamente como un diccionario (`{"142": 150000, "91": 0}`).
* **Diccionario Dinámico:** El modelo `CodigoF29` guarda los nombres (Glosas) de los códigos. Si el extractor detecta un código nuevo en el PDF, auto-rellena el input sugerido y lo guarda en la BD de forma transparente para el usuario.

#### 4. Motor de Auditoría y Cuadratura (`ReglaValidacion`)
* **Criterio:** El sistema no solo debe "guardar" datos, debe validarlos matemáticamente para buscar errores humanos en la declaración original.
* **Solución:** Se creó un motor de reglas administrable desde el Panel de Django (`/admin`). Permite configurar reglas como: *"Suma Códigos A y B, Resta Código C, el resultado debe ser igual al Código D"*.
* **Desglose Guardado:** La función `verificar_cuadratura()` calcula estas reglas y guarda el paso a paso matemático en un campo JSON (`detalles_cuadratura`), permitiendo mostrar un Pop-up en la interfaz con un estilo de "Boleta/Factura" detallando exactamente qué sumó, qué restó y la diferencia.

#### 5. Interfaz y Experiencia de Usuario (UI/UX)
* **Pantalla Dividida:** Se usa `<embed>` para visualizar el PDF cargado a la izquierda, mientras a la derecha se edita y confirma la información.
* **Limpieza Automática:** El PDF se guarda en `/media/tmp/` solo temporalmente. Al darle a "Guardar y Confirmar", la vista de Django elimina físicamente el archivo (`os.remove`) para ahorrar espacio en el servidor.
* **Prevención de Duplicados:** La vista bloquea el guardado si detecta que el `Folio` ingresado ya existe en la base de datos para cualquier otra declaración.
* **Edición Ágil:** Se permite agregar filas manuales (JavaScript) y editar un F29 ya guardado sin necesidad de volver a subir el PDF, recalculando la auditoría automáticamente al guardar.
* **Humanize:** Se integró `django.contrib.humanize` para que todos los montos en tablas y pop-ups se presenten con separador de miles (`|intcomma`), mejorando drásticamente la lectura contable.
* **Seguridad de iFrames:** Se agregó `X_FRAME_OPTIONS = 'SAMEORIGIN'` en `settings.py` para permitir la visualización de los PDFs locales en el navegador sin bloqueos de seguridad.