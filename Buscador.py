import os
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from ddgs import DDGS

# --- CONFIGURACIÓN DE CONSOLA ---
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

MOVIE_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv']
MAX_WORKERS = 4

# --- MAPA DE PAÍSES ---
COUNTRY_MAP = {
    'turcas': 'turca',
    'mexicanas': 'mexicana',
    'colombianas': 'colombiana',
    'brasileñas': 'brasileña',
    'españolas': 'española',
    'indias': 'india',
    'argentinas': 'argentina',
    'chilenas': 'chilena',
    'venezolanas': 'venezolana',
    'peruanas': 'peruana',
    'filipinas': 'filipina',
    'coreanas': 'coreana',
    'tailandesas': 'tailandesa',
    'estadounidenses': 'estadounidense',
    'puertorriqueñas': 'puertorriqueña'
}

# --- 1. RUTAS DE NOVELAS ---
NOVELA_PATHS = [
    r'G:\Novelas',
    r'J:\Novelas\Algo\Novelas\Nuevas novelas'
]

NOVELA_PATHS_LOWER = [p.lower() for p in NOVELA_PATHS]

# --- LISTA BLANCA DE CARPETAS CON POSTER ---
ALLOWED_POSTER_FOLDERS = [
    'animados',
    'filmes [colecciones especiales]',
    'filmes [colecciones x actores]',
    'filmes [colecciones x sagas]',
    'filmes [hd] [clasicos]',
    'filmes [hd] [estrenos]',
    'series [clasicas] [temporadas completas]',
    'series [tx] [temporadas finalizadas]',
    'series [tx] [temporadas finalizadas] [dobladas al español]',
    'series [tx] [temporadas finalizadas] [dual audio]',
    'series españolas [tx] [temporadas finalizadas]'
]

# ============================================================
# FUNCIONES AUXILIARES (sin cambios)
# ============================================================

def sanitize_filename(name):
    """Elimina caracteres inválidos para nombres de archivo."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean.strip()

def clean_title_for_grouping(text):
    """Limpia el nombre para agrupar Series/novelas."""
    title = text
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\]', '', title) 
    title = re.sub(r'\[.*', '', title) 
    
    title = re.sub(
        r'\b(cap\s*-\s*\d+|capitulo\s*\d+|ep\s*-\s*\d+|episodio\s*\d+|temp\s*\d+|temporada\s*\d+|s\d+e\d+|t\d+).*', 
        '', 
        title, 
        flags=re.IGNORECASE
    )
    
    title = re.sub(r'[._]', ' ', title)
    title = re.sub(r'\s*-\s*$', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title

def get_group_key(filename):
    base = os.path.splitext(filename)[0]
    clean_name = clean_title_for_grouping(base)
    return clean_name.strip().lower()

def detect_country_from_path(path_lower):
    for folder_keyword, country_adj in COUNTRY_MAP.items():
        if folder_keyword in path_lower:
            return country_adj
    return None

def is_allowed_poster_path(path_lower):
    """Verifica si la ruta está permitida para buscar pósters."""
    if any(path_lower.startswith(n_path) for n_path in NOVELA_PATHS_LOWER):
        return True
    
    for allowed in ALLOWED_POSTER_FOLDERS:
        if allowed in path_lower:
            return True
            
    return False

def get_movie_poster_url(name, search_type="movie", country_name=None):
    """Busca la URL de un póster basado en un nombre y la devuelve (sin descargar)."""
    try:
        base_name = os.path.splitext(name)[0]
        year_match = re.search(r'\[(\d{4})\]', base_name)
        year = year_match.group(1) if year_match else ""
        title = clean_title_for_grouping(base_name)
        
        if not title: return None

        if search_type == "novela":
            if country_name:
                query = f"{title} {year} {country_name} novela poster".strip()
            else:
                query = f"{title} {year} novela poster".strip()
        elif search_type == "cartoon":
            query = f"{title} {year} poster".strip()
        else:
            query = f"{title} {year} movie poster".strip()
            
        print(f"  🔍 [NUEVA BÚSQUEDA ({search_type.upper()})] '{query}'...")
        
        poster_url = None
        try:
            with DDGS() as ddgs:
                results = ddgs.images(query, region='wt-wt', safesearch='off', max_results=1)
            results_list = list(results)
            if results_list:
                poster_url = results_list[0]['image']
                print(f"  ✅ [URL OBTENIDA] para '{title}'")
                return poster_url
        except Exception as search_err:
            print(f"  ⚠️ Error en búsqueda '{title}': {search_err}")

        return None
    except Exception as e:
        print(f"  ❌ Error general procesando '{name}': {e}")
        return None

# ============================================================
# NUEVAS FUNCIONES PARA MODO INCREMENTAL
# ============================================================

def build_poster_index(node, base_path="", index=None):
    """
    Construye un índice: ruta_completa -> poster_url
    Recorre TODO el JSON existente y extrae los posters.
    """
    if index is None:
        index = {}
    
    node_type = node.get("type", "folder")
    node_name = node.get("name", "")
    
    # Construir ruta completa
    if base_path:
        current_path = os.path.join(base_path, node_name)
    else:
        current_path = node_name
    
    # Guardar poster si existe
    if "poster" in node and node["poster"]:
        index[current_path.lower()] = node["poster"]
    
    # Recorrer hijos
    for child in node.get("children", []):
        build_poster_index(child, current_path, index)
    
    return index


def load_existing_json(filename):
    """
    Carga el JSON existente y construye el índice de posters.
    Retorna: (datos_json, indice_posters)
    """
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Construir índice de posters
            poster_index = build_poster_index(data)
            
            print(f"📂 JSON existente cargado: {filename}")
            print(f"   📊 Posters cacheados: {len(poster_index)}")
            
            return data, poster_index
        except json.JSONDecodeError as e:
            print(f"⚠️ Error leyendo JSON (se creará nuevo): {e}")
        except Exception as e:
            print(f"⚠️ Error cargando JSON: {e}")
    
    return None, {}


# ============================================================
# FUNCIÓN DE ESCANEO INCREMENTAL (MODIFICADA)
# ============================================================

def scan_directory(path, poster_index, executor=None, parent_path="", stats=None):
    """
    Escanea directorios de forma INCREMENTAL.
    - Reutiliza posters del índice si existen
    - Solo busca posters NUEVOS para elementos que no los tienen
    """
    if stats is None:
        stats = {"reused": 0, "new_searches": 0, "errors": 0}
    
    folder_name = os.path.basename(os.path.normpath(path))
    node = {"name": folder_name, "type": "folder", "children": []}
    
    # Ruta lógica completa (para buscar en el índice)
    current_logical_path = os.path.join(parent_path, folder_name) if parent_path else folder_name
    current_path_lower = current_logical_path.lower()
    
    # Intentar obtener items del directorio
    try:
        items = sorted(os.listdir(path))
    except (PermissionError, FileNotFoundError):
        # Si no podemos acceder, al menos recuperar el poster si existe
        if current_path_lower in poster_index:
            node["poster"] = poster_index[current_path_lower]
            stats["reused"] += 1
        return node

    # Detectar permisos de póster para esta ruta
    is_novela_path = any(current_path_lower.startswith(n_path) for n_path in NOVELA_PATHS_LOWER)
    is_allowed = is_allowed_poster_path(current_path_lower)
    detected_country = detect_country_from_path(current_path_lower) if is_novela_path else None
    
    has_video_files = False
    if is_novela_path:
        has_video_files = any(os.path.splitext(i)[1].lower() in MOVIE_EXTENSIONS for i in items)

    futures_map = {}

    for item_name in items:
        full_path = os.path.join(path, item_name)
        item_logical_path = os.path.join(current_logical_path, item_name)
        item_path_lower = item_logical_path.lower()
        
        # Ignorar archivos del sistema
        if item_name.startswith('.') or item_name.startswith('$Recycle.Bin') or item_name.startswith('System Volume Information'):
            continue

        if os.path.isdir(full_path):
            # Escaneo recursivo
            child_node = scan_directory(full_path, poster_index, executor, current_logical_path, stats)
            node["children"].append(child_node)
        else:
            child_node = {"name": item_name, "type": "file"}
            
            # ✅ RECUPERAR POSTER DEL ÍNDICE SI EXISTE
            if item_path_lower in poster_index:
                child_node["poster"] = poster_index[item_path_lower]
                stats["reused"] += 1

            ext = os.path.splitext(item_name)[1].lower()
            
            if ext in MOVIE_EXTENSIONS and is_allowed:
                if not is_novela_path:
                    # ✅ SOLO BUSCAR SI NO TIENE POSTER
                    if "poster" not in child_node:
                        search_type = "movie"
                        if "animados" in current_path_lower:
                            search_type = "cartoon"
                        future = executor.submit(get_movie_poster_url, item_name, search_type, None)
                        futures_map[future] = child_node
                        stats["new_searches"] += 1

            node["children"].append(child_node)

    # --- GESTIÓN DE BÚSQUEDA DE CARPETAS EN NOVELAS ---
    if is_novela_path and has_video_files:
        # ✅ RECUPERAR POSTER DE CARPETA DEL ÍNDICE
        if current_path_lower in poster_index:
            node["poster"] = poster_index[current_path_lower]
            stats["reused"] += 1
        
        # ✅ SOLO BUSCAR SI NO TIENE POSTER
        if "poster" not in node:
            skip_keywords = ['animados', 'novelas', 'filmes']
            is_container_folder = any(keyword in folder_name.lower() for keyword in skip_keywords)
            if not is_container_folder:
                future = executor.submit(get_movie_poster_url, folder_name, "novela", detected_country)
                futures_map[future] = node
                stats["new_searches"] += 1

    # --- ESPERAR HILOS ---
    if futures_map:
        for future in as_completed(futures_map):
            target_node = futures_map[future] 
            try:
                poster_url = future.result()
                if poster_url:
                    target_node["poster"] = poster_url
            except Exception as e:
                print(f"  ❌ Error en hilo '{target_node['name']}': {e}")
                stats["errors"] += 1

    # --- PROPAGACIÓN DE POSTER A ARCHIVOS (VISUAL) ---
    if "poster" in node and node.get("children"):
        for child in node["children"]:
            if child.get("type") == "file" and "poster" not in child:
                ext = os.path.splitext(child["name"])[1].lower()
                if ext in MOVIE_EXTENSIONS:
                    child["poster"] = node["poster"]

    # --- LÓGICA DE HERENCIA (Carpetas Madre) ---
    if is_allowed and "poster" not in node and node.get("children"):
        for child in node["children"]:
            if "poster" in child and child["poster"]:
                node["poster"] = child["poster"]
                break

    return node


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def main():
    output_filename = 'directory_structure_local.json'
    
    # ✅ CARGAR JSON EXISTENTE Y CONSTRUIR ÍNDICE
    existing_data, poster_index = load_existing_json(output_filename)
    
    base_drives = NOVELA_PATHS[:] 
    
    print("\n--- ¿Quieres añadir rutas adicionales (Filmes, Series, etc)? ---")
    print("    (Deja vacío para usar solo las rutas configuradas)")
    while True:
        path_input = input("Ruta (ej: G:\\Filmes): ").strip()
        if not path_input:
            break
        if os.path.isdir(path_input):
            base_drives.append(path_input)
            print(f"   ✅ Añadida: {path_input}")
        else:
            print(f"   ❌ Ruta inválida o no existe.")
    
    if not base_drives:
        print("\n❌ Sin rutas válidas.")
        return

    # Estadísticas
    stats = {"reused": 0, "new_searches": 0, "errors": 0}

    print(f"\n{'='*60}")
    print(f"   MODO INCREMENTAL ACTIVADO")
    print(f"   Posters cacheados: {len(poster_index)}")
    print(f"   Hilos: {MAX_WORKERS}")
    print(f"{'='*60}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        root_structure = {"name": "Mis Archivos", "type": "folder", "children": []}

        for path in base_drives:
            print(f"\n📁 Escaneando: {path}...")
            scanned_node = scan_directory(path, poster_index, executor, stats=stats)
            if scanned_node:
                root_structure["children"].append(scanned_node)
    
    if not root_structure["children"]:
        print("\n❌ No se encontraron archivos.")
        return

    # Guardar resultado
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(root_structure, f, ensure_ascii=False, indent=2)
    
    # Mostrar resumen
    print(f"\n{'='*60}")
    print(f"   📊 RESUMEN")
    print(f"{'='*60}")
    print(f"   ✅ Posters reutilizados:  {stats['reused']}")
    print(f"   🔍 Búsquedas nuevas:      {stats['new_searches']}")
    print(f"   ❌ Errores:               {stats['errors']}")
    print(f"{'='*60}")
    print(f"\n🎉 ¡Listo! Guardado en: {output_filename}")


if __name__ == "__main__":
    main()