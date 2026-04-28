# Bitácora de Desarrollo - ContaCarvajal ERP

## ⚠️ Reglas de Trabajo y Prompting (¡LEER SIEMPRE PRIMERO!)
1. **Debatir antes de codificar:** Antes de generar código, proponer la solución, explicar el "por qué" y debatir si es la mejor alternativa.
2. **Estructura Estricta y Ordenada:** Mantener el orden modular del proyecto. No crear archivos en lugares aleatorios o que rompan la arquitectura.
3. **Delegación de Carpetas:** Si se requiere una nueva carpeta, indicar la ruta exacta al desarrollador para que él la cree. Solo continuar cuando el directorio exista.
4. **Preservar Formatos:** Respetar los formatos existentes de UI/UX, plantillas HTML, clases de Bootstrap y convenciones de nombres.
5. **Restricción por Roles (RBAC):** Más adelante, cada "submódulo" o funcionalidad específica deberá estar restringida o adaptada dependiendo de los roles del usuario (Admin vs Cliente vs Staff). Nunca asumir que un usuario tiene acceso a todo sin validarlo.

---

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

### Fecha: 28 de Abril de 2026
**Resumen:** Automatización de Superusuario y personalización de la página de Login.

#### 1. Creación de Superusuario por Defecto
* **Decisión:** Se optó por la **Opción A (Señales de Django)**. Se utilizará la señal `post_migrate` para verificar la existencia del superusuario "Carlos" cada vez que se ejecuten las migraciones.
* **Justificación:** Es un método robusto y automático. El código se diseñó para que **solo cree el usuario si no existe**, evitando así sobreescribir la contraseña si esta se cambia manualmente en el futuro.

#### 2. Página de Inicio de Sesión Profesional
* **Decisión:** Se sobreescribirá la plantilla de login por defecto de Django.
* **Justificación:** Siguiendo la convención de Django, se crea el archivo `templates/registration/login.html`. El motor de plantillas de Django priorizará este archivo sobre el que viene por defecto, permitiendo una personalización completa sin tocar el núcleo del framework.

### Fecha: [Fase de Planificación] 
**Resumen:** Módulo de Plan de Cuentas y Centralización Automática de F29
* **Objetivo:** Permitir la creación de Planes de Cuentas bajo norma chilena por empresa.
* **Contabilidad Simplificada vs Completa:** Se establece que este método de centralización vía F29 será el de "Contabilidad Simplificada". La arquitectura dejará preparado el terreno para un futuro módulo de captura por "Registro de Compra y Ventas (RCV)" para "Contabilidad Completa".
* **Carga Masiva (Plan Base):** Se implementó un diccionario hardcodeado en Python (`plan_base.py`) con el estándar contable chileno. Permite cargar masivamente cuentas agrupadas (Activos, Pasivos, etc.) sugiriendo cuentas obligatorias marcadas por defecto, evitando la digitación manual.
* **Motor de Fórmulas:** Sistema de plantillas de centralización donde el usuario pueda usar variables de códigos SII (Ej: `([520] / 19) * 100`) para calcular cuentas y automatizar asientos.
* **Partida Doble:** Modelos `AsientoContable` y `LineaAsiento` para respetar el Debe y Haber. El origen del asiento estará vinculado dinámicamente (ahora al F29, a futuro al RCV).
* **Clonación de Plantillas (RBAC):** Se implementó una función exclusiva para Administradores que permite copiar una plantilla de una empresa a otra. El sistema realiza un "mapeo inteligente" buscando la equivalencia de cuentas por su Código (Ej: 1.1.01) en la empresa de destino.
* **Procesador Matemático Seguro y Vista Previa:** Función que lee fórmulas y ejecuta las matemáticas. Se implementó un paso de "Previsualización" (Pop-up) obligatorio. El usuario debe ver el asiento cuadrado antes de que se grabe en la base de datos.
* **Edición de Plantillas (Erase & Replace):** Para la edición de plantillas con filas dinámicas en JS, el backend elimina las líneas antiguas y re-inserta las enviadas por el formulario para asegurar coherencia absoluta.
* **Estrategia de Centralización:** Se aconseja y permite la aplicación de múltiples plantillas separadas (Compras, Ventas, etc.) a un mismo F29 para mantener la granularidad y limpieza del Libro Diario, en lugar de "Mega Asientos".
* **Auditoría de Prevención:** Se agregó en el Historial de F29 y en el motor de centralización un sistema de alertas que detecta e informa si un F29 ya posee Asientos Contables vinculados, evitando la duplicación de partidas.

### Fecha: [Fase de Planificación]
**Resumen:** Refactorización de Navegación (Enfoque "Contexto de Empresa")
* **Problema:** La navegación actual es "Módulo -> Todas las Empresas". Esto es desordenado y poco escalable para un Administrador.
* **Solución Propuesta:** Invertir la navegación a "Empresa -> Módulos". 
* **Mecanismo:** Implementar un "Contexto de Empresa" usando `request.session`. El Admin selecciona una empresa en el Home, el sistema la guarda en sesión, y redirige a un "Dashboard de Empresa" con accesos rápidos. El cliente entra directo a su Dashboard. El Menú Lateral (`base.html`) y las vistas se adaptarán dinámicamente a la empresa en sesión.

---

## Próximos Pasos (Pendientes para la siguiente sesión)
1. **Exportación a PDF del Comprobante Contable:** Implementar un botón en la vista de detalle del Asiento (Libro Diario) para generar un PDF descargable con el formato de la "Tabla T" y sus glosas, ideal para respaldos físicos o envíos al cliente.
2. **Módulo de Libro Mayor:** Crear una vista interactiva donde el usuario pueda seleccionar una Cuenta Contable específica (Ej: "Caja" o "Mercaderías") y auditar todo su historial de movimientos (cargos y abonos), calculando su saldo final en tiempo real.
3. **Centralización Masiva (Multi-período):** Desarrollar la funcionalidad para ejecutar varias plantillas sobre múltiples períodos (F29) en bloque, agilizando la carga de contabilidad atrasada.
4. **Libro de Caja:** Crear un reporte de flujo (ingresos menos salidas) que permita contrastar de forma resumida las ventas versus las compras y el pago de honorarios.