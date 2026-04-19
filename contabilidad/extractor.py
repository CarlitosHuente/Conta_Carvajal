import fitz  # PyMuPDF
import re

def extraer_datos_f29(ruta_pdf):
    """
    Abre un PDF del SII, extrae su texto y busca el RUT, Folio y Códigos.
    Retorna un diccionario con los datos listos para comparar.
    """
    # 1. Abrimos el documento PDF
    doc = fitz.open(ruta_pdf)
    texto_completo = ""
    
    # Leemos todas las páginas (el F29 suele ser 1, pero por si acaso)
    for pagina in doc:
        texto_completo += pagina.get_text("text") + "\n"
        
    doc.close()

    datos = {
        "rut": None,
        "folio": None,
        "mes": None,
        "ano": None,
        "codigos": {},
        "glosas": {}  # Guardaremos los nombres de los códigos para autocompletar
    }

    # 2. Rescatar el RUT (Regla: después de [03])
    # Usamos (?:\[03\]|03) por si PyMuPDF omite los corchetes al leer
    match_rut = re.search(r'(?:\[03\]|03)\s*([\d\.]+-[0-9Kk])', texto_completo)
    if match_rut:
        datos["rut"] = match_rut.group(1).replace(".", "").upper()

    # 3. Rescatar el Folio (Regla: después de [07])
    match_folio = re.search(r'(?:\[07\]|07)\s*(\d+)', texto_completo)
    if match_folio:
        datos["folio"] = match_folio.group(1)

    # 4. Rescatar el Período (Regla: después de [15])
    match_periodo = re.search(r'(?:\[15\]|15)\s*(\d{4})(\d{2})', texto_completo)
    if match_periodo:
        datos["ano"] = int(match_periodo.group(1))
        datos["mes"] = int(match_periodo.group(2))

    # 5. Delimitar la zona útil (Regla: Empezar a capturar después de "Glosa" o "Valor")
    match_inicio = re.search(r'\b(?:Glosa|Valor)\b', texto_completo, re.IGNORECASE)
    if match_inicio:
        texto_util = texto_completo[match_inicio.end():]
    else:
        texto_util = texto_completo

    # 6. Rescatar Códigos, Glosas y Valores
    # Al anclar la expresión al final de la línea ($) y quitar el ".*", obligamos a que 
    # el valor sea el ÚLTIMO dato. Así ignorará los números que estén dentro de la glosa.
    patron_codigos = re.finditer(r'^(\d{2,4})\s+(.+?)\s+((?:\d{1,3}(?:\.\d{3})*|\d+))(?:\s*\+)?\s*$', texto_util, re.MULTILINE)
    
    for match in patron_codigos:
        codigo = match.group(1)
        glosa = match.group(2).strip()
        valor_str = match.group(3).replace(".", "")
        
        try:
            valor_int = int(valor_str)
            
            # Regla de Término y Excepción: El Código 91 SIEMPRE se guarda (incluso si es 0)
            if codigo == "91" or codigo == "091":
                datos["codigos"]["91"] = valor_int
                datos["glosas"]["91"] = glosa
                break

            # Regla: Si el monto es 0 o menor, no lo incluimos
            if valor_int <= 0:
                continue
                
            datos["codigos"][codigo] = valor_int
            datos["glosas"][codigo] = glosa
        except ValueError:
            continue # Si no es un número válido, lo saltamos
            
    # 7. Rescate de emergencia para el código 91
    # Si el formato de la última línea estaba muy roto y el loop no lo leyó, lo forzamos.
    if "91" not in datos["codigos"]:
        # Buscamos TODAS las apariciones del 91 y tomamos la última.
        # [^\d]{0,30}? permite que haya hasta 30 caracteres basura o saltos de línea antes del monto.
        matches_91 = re.findall(r'\b(?:91|091)\b[^\d]{0,30}?((?:\d{1,3}(?:\.\d{3})*|\d+))', texto_completo)
        if matches_91:
            try:
                # Tomamos el último match de la lista (que siempre es el total final del documento)
                datos["codigos"]["91"] = int(matches_91[-1].replace(".", ""))
                datos["glosas"]["91"] = "Total a Pagar"
            except ValueError:
                pass

    return datos, texto_completo