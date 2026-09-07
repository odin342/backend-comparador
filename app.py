import json
import re
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# ==========================================
SCRAPERAPI_KEY = "ffed8880e2e45f1789bd6e0379c65b0b"
SUPABASE_URL = "https://jqvodxitphzyuizfhkyj.supabase.co"
SUPABASE_KEY = "sb_secret_LbtjYgX3-YPg1Idfj0HGcQ_Fv8kx503"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- AQUÍ VA LA CONFIGURACIÓN DE CORS ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite peticiones desde Netlify y cualquier origen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -----------------------------------------

class SolicitudProducto(BaseModel):
    url_amazon: str

# ==========================================
# 2. FUNCIONES DE BÚSQUEDA Y EXTRACCIÓN
# ==========================================

def buscar_url_en_amazon(busqueda: str):
    """ Busca un texto en Amazon y devuelve la URL del primer producto relevante """
    print(f"Buscando en Amazon automáticamente: '{busqueda}'...")
    url_busqueda = f"https://www.amazon.com/s?k={quote_plus(busqueda)}"
    
    payload = {
        'api_key': SCRAPERAPI_KEY,
        'url': url_busqueda,
        'country_code': 'us'
    }
    
    response = requests.get('http://api.scraperapi.com', params=payload)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    resultado = soup.find('div', {'data-component-type': 's-search-result'})
    if resultado:
        enlace = resultado.find('a', class_='a-link-normal s-no-hover s-underline-text s-underline-link-text s-link-style a-text-normal') or resultado.find('a', class_='a-link-normal')
        if enlace and 'href' in enlace.attrs:
            href = enlace['href']
            if href.startswith('/'):
                return f"https://www.amazon.com{href}"
            return href
            
    return None


def detectar_categoria_id(nombre_producto: str, soup: BeautifulSoup) -> int:
    nombre_lower = nombre_producto.lower()

    # A. Detectar palabras clave en el título para las 12 categorías
    if any(p in nombre_lower for p in ["phone", "celular", "smartphone", "iphone", "galaxy", "xiaomi"]):
        return 1  # Celulares
    elif any(p in nombre_lower for p in ["mouse", "ratón", "trackball"]):
        return 2  # Mouses
    elif any(p in nombre_lower for p in ["keyboard", "teclado", "keypad"]):
        return 3  # Teclados
    elif any(p in nombre_lower for p in ["tv", "television", "televisor", "smart tv"]):
        return 4  # Televisores
    elif any(p in nombre_lower for p in ["laptop", "notebook", "macbook", "portátil"]):
        return 5  # Portatiles
    elif any(p in nombre_lower for p in ["headset", "headphones", "audífonos", "auriculares", "diadema"]):
        return 6  # Diademas
    elif any(p in nombre_lower for p in ["motherboard", "b550", "z790", "board", "placa madre"]):
        return 7  # Board
    elif any(p in nombre_lower for p in ["ddr4", "ddr5", "ram", "memory"]):
        return 8  # Ram
    elif any(p in nombre_lower for p in ["rtx", "rx", "gpu", "graphics card", "tarjeta de video"]):
        return 9  # Tarjeta De Video
    elif any(p in nombre_lower for p in ["monitor", "display", "screen"]):
        return 10 # Monitores
    elif any(p in nombre_lower for p in ["ssd", "hdd", "nvme", "disco duro", "storage"]):
        return 11 # Disco Duro
    elif any(p in nombre_lower for p in ["ipad", "tab", "tablet"]):
        return 12 # Tablet

    # B. Buscar en la ruta de categorías de Amazon si el título no es claro
    breadcrumbs = soup.find(id="wayfinding-breadcrumbs_feature_div")
    if breadcrumbs:
        texto_ruta = breadcrumbs.get_text().lower()
        if "cell phones" in texto_ruta:
            return 1
        elif "mouse" in texto_ruta or "input devices" in texto_ruta:
            return 2
        elif "keyboard" in texto_ruta:
            return 3
        elif "television" in texto_ruta or "tv" in texto_ruta:
            return 4
        elif "laptop" in texto_ruta or "computers" in texto_ruta:
            return 5
        elif "headphone" in texto_ruta or "audio" in texto_ruta:
            return 6
        elif "motherboards" in texto_ruta:
            return 7
        elif "memory" in texto_ruta:
            return 8
        elif "graphics cards" in texto_ruta:
            return 9
        elif "monitors" in texto_ruta:
            return 10
        elif "drives" in texto_ruta or "storage" in texto_ruta:
            return 11
        elif "tablets" in texto_ruta:
            return 12

    return 1  # Categoría por defecto si no logra identificar el tipo


def extraer_de_amazon(url_amazon: str):
    """ Extrae los datos y especificaciones de la página de un producto en Amazon """
    payload = {
        'api_key': SCRAPERAPI_KEY,
        'url': url_amazon,
        'country_code': 'us',
        'render': 'true'
    }
    response = requests.get('http://api.scraperapi.com', params=payload)
    if response.status_code != 200:
        return None

    html_text = response.text
    soup = BeautifulSoup(html_text, 'html.parser')

    # Título
    titulo_elem = soup.find(id="productTitle")
    nombre = titulo_elem.get_text().strip() if titulo_elem else "Producto Amazon"

    # Precio
    precio = 0.0
    precio_elem = soup.find("span", class_="a-offscreen") or soup.find(id="priceblock_ourprice")
    if precio_elem:
        precio_texto = precio_elem.get_text().replace(',', '')
        match = re.search(r'\d+\.\d+|\d+', precio_texto)
        if match:
            precio = float(match.group())

    # Calificación
    calificacion = "⭐ N/A"
    patron_rating = re.search(r'(\d[\.,]\d)\s*(out of 5 stars|de 5 estrellas|de 5)', html_text, re.IGNORECASE)
    
    if patron_rating:
        nota = patron_rating.group(1).replace(',', '.')
        calificacion = f"⭐ {nota} / 5"
    else:
        rating_elem = soup.find("span", class_="a-icon-alt") or soup.find("i", class_="a-icon-star")
        if rating_elem:
            texto = rating_elem.get_text()
            match = re.search(r'(\d+[\.,]?\d*)', texto)
            if match:
                calificacion = f"⭐ {match.group(1).replace(',', '.')} / 5"

    # Especificaciones
    especificaciones = {}
    tabla_specs = soup.find("table", class_="a-keyvalue") or soup.find(id="productDetails_techSpec_section_1")
    if tabla_specs:
        for fila in tabla_specs.find_all("tr"):
            k, v = fila.find("th"), fila.find("td")
            if k and v:
                especificaciones[k.get_text().strip()] = v.get_text().strip().replace('\u200e', '')

    if not especificaciones:
        for fila in soup.find_all("tr", class_="po-row"):
            k = fila.find("td", class_="a-span3") or fila.find("span", class_="a-size-base a-color-base")
            v = fila.find("td", class_="a-span9") or fila.find("span", class_="a-size-base a-color-tertiary")
            if k and v:
                especificaciones[k.get_text().strip()] = v.get_text().strip().replace('\u200e', '')

    slug = re.sub(r'[^a-z0-9]+', '-', nombre.lower()).strip('-')[:50]

    return {
        "nombre": nombre[:100],
        "slug": slug,
        "precio": precio,
        "calificacion": calificacion,
        "categoria_id": detectar_categoria_id(nombre, soup),
        "especificaciones": especificaciones
    }

# ==========================================
# 3. RUTAS API DE FASTAPI
# ==========================================

@app.get("/api/sugerencias")
async def obtener_sugerencias(q: str = ""):
    texto = q.strip()
    if not texto or len(texto) < 2:
        return []
    
    res = supabase.table('productos').select('nombre').ilike('nombre', f"%{texto}%").limit(5).execute()
    if res.data:
        return list(set([item['nombre'] for item in res.data]))
    return []


@app.post("/api/obtener-producto")
async def obtener_producto(req: SolicitudProducto):
    entrada = req.url_amazon.strip()

    if "amazon." in entrada:
        producto_datos = extraer_de_amazon(entrada)
        if not producto_datos:
            raise HTTPException(status_code=400, detail="No se pudo extraer la información del enlace.")
        supabase.table('productos').upsert(producto_datos, on_conflict='slug').execute()
        return producto_datos

    res = supabase.table('productos').select('*').ilike('nombre', f"%{entrada}%").limit(1).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]

    url_encontrada = buscar_url_en_amazon(entrada)
    if url_encontrada:
        producto_datos = extraer_de_amazon(url_encontrada)
        if producto_datos:
            supabase.table('productos').upsert(producto_datos, on_conflict='slug').execute()
            return producto_datos

    raise HTTPException(status_code=404, detail=f"No se encontró información para '{entrada}'.")