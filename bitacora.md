# Bitácora de Desarrollo - ContaCarvajal ERP

## ⚠️ Reglas de Trabajo y Prompting (¡LEER SIEMPRE PRIMERO!)
1. **Debatir antes de codificar:** Antes de generar código, proponer la solución, explicar el "por qué" y debatir si es la mejor alternativa.
2. **Estructura Estricta y Ordenada:** Mantener el orden modular del proyecto. No crear archivos en lugares aleatorios o que rompan la arquitectura.
3. **Delegación de Carpetas:** Si se requiere una nueva carpeta, indicar la ruta exacta al desarrollador para que él la cree. Solo continuar cuando el directorio exista.
4. **Preservar Formatos:** Respetar los formatos existentes de UI/UX, plantillas HTML, clases de Bootstrap y convenciones de nombres.
5. **Restricción por Roles (RBAC):** Más adelante, cada "submódulo" o funcionalidad específica deberá estar restringida o adaptada dependiendo de los roles del usuario (Admin vs Cliente vs Staff). Nunca asumir que un usuario tiene acceso a todo sin validarlo.
6. **Estructura Estricta de Templates (Django):** Todos los archivos HTML deben ir obligatoriamente dentro de la ruta `app_name/templates/app_name/` (o en subcarpetas dentro de esta). NUNCA dejar archivos HTML en la raíz de la aplicación.

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

### Fecha: 30 de Abril de 2026
**Resumen:** Avances Core en RR.HH (Novedades, Ítems Fijos e Indicadores Económicos)
* **Novedades Mensuales:** Creación de vista tipo "Excel" para carga rápida de inasistencias, licencias y bonos/descuentos esporádicos. Los bonos esporádicos se tratan como montos "Líquidos" que el motor deberá inflar (Grossing Up).
* **Ítems Fijos de Contrato:** Implementación de `ItemContrato` para administrar bonos o descuentos recurrentes mes a mes por trabajador.
* **Indicadores Económicos e Históricos:** 
  * Integración de script de carga histórica de datos base Previred (Topes, Sueldo Mínimo, SIS).
  * Lógica de "Herencia": Bucle inteligente que propaga topes conocidos hacia meses futuros.
  * Integración de API `mindicador.cl`: Botón en el formulario que consume la API para autocompletar UF y UTM, disparando un cálculo en JS en tiempo real para obtener los topes en pesos chilenos.
* **Conceptos Variables y Tramos:** Arquitectura avanzada para bonos y comisiones. Se permiten reglas de "Porcentaje Fijo" o "Tramos Escalonados". Los conceptos se habilitan desde el `Contrato` del trabajador, lo que genera dinámicamente columnas de ingreso de bases en la pantalla de Novedades.
* **Motor de Remuneraciones:** Desarrollo del núcleo matemático. Aplica topes imponibles, calcula Impuesto Único de 2da Categoría, determina valores históricos de tasas AFP (fotografía inmutable) y consolida el Sueldo Líquido. Se conectó a una vista de procesamiento masivo.
* **Reportes y Comprobantes (Cierre RR.HH):** Se implementó la vista optimizada para impresión nativa del PDF de la liquidación de sueldo y la pantalla del Libro de Remuneraciones, consolidando todos los montos imponibles, descuentos y el líquido a pagar por período.

---

## Próximos Pasos (Pendientes para la siguiente sesión)
1. **Exportación a PDF del Comprobante Contable:** Implementar la vista imprimible del Asiento en el Libro Diario.
2. **Módulo de Libro Mayor:** Vista interactiva para auditar cuentas contables.
3. **Centralización Masiva:** Ejecutar plantillas sobre múltiples F29 en bloque.
4. **Libro de Caja:** Reporte de flujo (Ingresos vs Egresos).

---

### Fecha: 30 de Abril de 2026 (Definición de Negocio RR.HH)
**Resumen:** Emisión Masiva de Liquidaciones para Clientes Migrados desde otros Estudios Contables

* **Contexto de Negocio:** Al captar clientes de la competencia, frecuentemente existen trabajadores activos sin historial formal de liquidaciones emitidas en sistema. Se requiere un flujo de regularización rápida y segura para emitir liquidaciones en bloque.
* **Objetivo Principal:** Permitir al contador generar liquidaciones masivas de forma práctica, guiada y con mínima fricción operativa, priorizando velocidad de carga para casos estándar.
* **Criterio Funcional:** Si falta información crítica para el cálculo, el sistema debe detectarlo y solicitarla de forma asistida (paso a paso), en lugar de bloquear con errores técnicos.
* **Modo Asistido (Wizard/Prompt):** Flujo interactivo por período (ej: Enero 2026) que pregunte solo variables faltantes por trabajador o por lote (días trabajados, bono especial, etc.), permitiendo responder rápido (Sí/No, monto, Enter para continuar).
* **Estrategia Operativa:** 
  * Caso estándar: emisión masiva directa con valores por defecto/plantilla.
  * Caso no estándar: activación de asistente para completar datos faltantes y continuar el proceso sin salir del flujo.
* **Validaciones Obligatorias Previas a Emisión:**
  * Contrato vigente por trabajador.
  * Indicadores económicos del período disponibles.
  * Datos mínimos completos para cálculo (o captura asistida antes de continuar).
* **Salida Esperada:** Generación completa de liquidaciones del período para todos los trabajadores seleccionados, con trazabilidad de qué datos fueron inferidos, heredados o ingresados manualmente.
* **Meta UX:** "Menos clics, más productividad contable": foco en teclado, preguntas contextuales y confirmación final antes de emitir en bloque.

---

### Fecha: 30 de Abril de 2026 (Definición Estratégica de Accesos, Planes y Clientes)
**Resumen:** Control granular por módulo/submódulo para clientes, según plan contratado, administrado por Superusuario

* **Visión del Negocio:** Como contador y superusuario, se requiere administrar múltiples empresas clientes con distintos niveles de acceso al ERP, según el plan contratado y servicios activos.
* **Objetivo Principal:** Entregar a cada cliente acceso exclusivo a su empresa, con permisos de solo visualización o uso operativo según corresponda (balances, liquidaciones, reportes y submódulos específicos).
* **Principio de Seguridad:** Ningún usuario cliente debe poder acceder a empresas ajenas ni a funcionalidades no contratadas/permitidas.
* **Modelo de Control Requerido:** 
  * Nivel 1: Acceso por empresa (aislamiento de datos por tenant).
  * Nivel 2: Acceso por módulo (RR.HH, Contabilidad, etc.).
  * Nivel 3: Acceso por submódulo/función puntual (ej: ver liquidaciones, ver balances, centralizar, editar, exportar).
  * Nivel 4: Tipo de permiso (Ver, Crear, Editar, Eliminar, Exportar, Administrar).
* **Componente Comercial (Planes):** Definir planes por empresa que habiliten/deshabiliten automáticamente módulos y submódulos disponibles para sus usuarios.
* **Componente de Administración:** El Superusuario debe poder:
  * Crear y administrar planes.
  * Asignar plan a cada empresa.
  * Asignar permisos adicionales/excepciones por usuario.
  * Ver trazabilidad de accesos y cambios de permisos.
* **Roadmap Comercial Futuro:** Preparar arquitectura para correo corporativo por dominio y módulos especiales a medida por requerimiento de clientes.
* **Meta Operativa:** Pasar de un RBAC básico a un sistema de autorizaciones multiempresa y monetizable por plan, manteniendo simplicidad de administración para el contador.

### Fecha: 30 de Abril de 2026 (Implementación Fase 1 de Permisos)
**Resumen:** Base funcional de control de acceso por módulo/submódulo en empresa activa.

* **Modelo Nuevo (`core.PermisoAccesoUsuario`):** Se implementa tabla de permisos por `usuario + empresa + modulo + submodulo + accion`, con bandera `permitido`.
* **Acciones Soportadas:** `ver`, `crear`, `editar`, `eliminar`, `exportar`, `administrar`.
* **Decorador de Seguridad:** Se crea `require_access(...)` en `core/permissions.py`, que valida empresa activa en sesión y permiso del usuario antes de entrar a la vista.
* **Regla de Jerarquía:** Superusuario/Admin mantiene acceso total. Usuarios cliente quedan sujetos a permisos explícitos por empresa.
* **Primeras Vistas Protegidas (MVP):**
  * RR.HH: `trabajadores` (ver), `liquidaciones` (crear/ver), `novedades` (editar).
  * Contabilidad: `f29` (ver/crear).
* **Backoffice de Administración:** Permisos visibles y administrables desde Django Admin (`core/admin.py`).
* **Próximo Paso Técnico:** Agregar permisos en menú (`base.html`) para ocultar opciones no autorizadas y completar cobertura en el resto de vistas críticas.

### Fecha: 3 de Mayo de 2026
**Resumen:** Estabilidad en producción (HostingChile), contratos, motor de liquidaciones y datos de liquidación para comprobantes.

#### 1. Producción y despliegue (cPanel / SSH)
* **`CSRF_TRUSTED_ORIGINS`:** Dominios HTTPS públicos en `settings.py` para evitar 403 al guardar formularios POST en producción.
* **Contrato:** `form.save_m2m()` tras crear contrato (conceptos variables). Plantilla: re-habilitar campos `disabled` en `submit` para que el POST sea válido; modal Bootstrap con errores si el formulario no valida; redirección a ficha del trabajador con ancla `#lista-contratos` y mensaje de éxito.
* **`core/apps.py` y `core/signals.py`:** Corrección `PerfilUsuario.objects.get_or_create(user=user)` (antes usaba `usuario`, inválido).
* **Operación en servidor:** Proyecto bajo `/home/contaca3/repositories/erp_sistema`; usar el Python del virtualenv (`.../virtualenv/.../bin/python`) para `migrate` y comandos Django, no el `python3` del sistema sin dependencias.

#### 2. Plan de salud y contrato (UF / Isapre)
* **Modelo:** `plan_salud_pactado` ampliado a **3 decimales** y mayor `max_digits` (migración `0006`).
* **Formulario:** Normalización de coma/punto y miles; widget de texto para el plan (evita bloqueo del navegador con `type="number"`).

#### 3. Motor de remuneraciones (`motor_remuneraciones.py`)
* **`fecha_emision`:** Al generar la liquidación, se fija el **último día del mes** del período liquidado (no la fecha de ejecución del proceso).
* **Gratificación legal (tipo LEGAL):** Documentado en código: base del **25%** sobre imponible acumulado hasta ese paso (sueldo proporcional, bono brutificado, ítems imponibles); **tope** `(sueldo_mínimo del indicador × 4,75) / 12`. Los haberes por conceptos variables se calculan **después** de la gratificación (no entran hoy en esa base).
* **Impuesto único (base tributable):** Se rebajan AFP, cesantía y solo el **7% legal** de salud sobre el imponible tope; el descuento de caja por Isapre mayor al 7% **no** reduce adicionalmente la base del IU (criterio habitual art. 43 LIR; líquido sigue descontando el plan real).

#### 4. Contrato y liquidación (comprobante)
* **Contrato:** Campo **`cargo`** (texto, opcional). Listado de contratos en ficha del trabajador y admin.
* **Liquidación (snapshot):** `fecha_ingreso_contrato` y `cargo_contrato` copiados al emitir; migración `0007` con **RunPython** que rellena liquidaciones antiguas desde el contrato vinculado (sin borrar datos).
* **Ítem “Salud” en liquidación:** Etiqueta tipo AFP con valor del plan, p. ej. `Salud Consalud (3.357 UF)` o plan en CLP / `(7%)` en Fonasa.
* **Plantillas:** Detalle y PDF de liquidación muestran cargo y fecha de ingreso; contrato formulario incluye cargo.

#### 5. Control de versiones
* Cambios subidos a repositorio remoto `main` en GitHub (`Conta_Carvajal`); en producción: `git pull` + `migrate` + reinicio de aplicación (p. ej. `tmp/restart.txt`).