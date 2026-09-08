import json
import re
import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# ==========================================
# REEMPLAZA ESTOS VALORES CON TUS CREDENCIALES REALES
SCRAPERAPI_KEY = "ffed8880e2e45f1789bd6e0379c65b0b"
SUPABASE_URL = "https://jqvodxitphzyuizfhkyj.supabase.co"
SUPABASE_KEY = "sb_secret_LbtjYgX3-YPg1Idfj0HGcQ_Fv8kx503"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. INICIALIZACIÓN DE FASTAPI Y CORS
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Captura de errores globales para garantizar cabeceras CORS en respuestas de error
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detalle": "Error interno en el servidor", "error": str(exc)}
    )

class SolicitudProducto(BaseModel):
    url_amazon: str

# ==========================================
# 3. FUNCIONES DE BÚSQUEDA Y EXTRACCIÓN
# ==========================================

def buscar_url_en_amazon(busqueda: str):
    url_busqueda = f"https://www.amazon.com/s?k={quote_plus(busqueda)}"
    payload = {
        'api_key': SCRAPERAPI_KEY,
        'url': url_busqueda,
        'country_code': 'us'
    }
    try:
        response = requests.get('http://api.scraperapi.com', params=payload, timeout=25)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        resultado = soup.find('div', {'data-component-type': 's-search-result'})
        if resultado:
            enlace = resultado.find('a', class_='a-link-normal s-no-hover s-underline-text s-underline-link-text s-link-style a-text-normal') or resultado.find('a', class_='a-link-normal')
            if enlace and 'href' in enlace.attrs:
                href = enlace['href']
                return f"https://www.amazon.com{href}" if href.startswith('/') else href
    except Exception:
        pass
    return None

def detectar_categoria_id(nombre_producto: str, soup: BeautifulSoup) -> int:
    nombre_lower = nombre_producto.lower()
    if any(p in nombre_lower for p in ["phone", "celular", "smartphone", "iphone", "galaxy", "xiaomi"]):
        return 1
    elif any(p in nombre_lower for p in ["mouse", "ratón", "trackball"]):
        return 2
    elif any(p in nombre_lower for p in ["keyboard", "teclado", "keypad"]):
        return 3
    elif any(p in nombre_lower for p in ["tv", "television", "televisor", "smart tv"]):
        return 4
    elif any(p in nombre_lower for p in ["laptop", "notebook", "macbook", "portátil"]):
        return 5
    elif any(p in nombre_lower for p in ["headset", "headphones", "audífonos", "auriculares", "diadema"]):
        return 6
    elif any(p in nombre_lower for p in ["motherboard", "b550", "z790", "board", "placa madre"]):
        return 7
    elif any(p in nombre_lower for p in ["ddr4", "ddr5", "ram", "memory"]):
        return 8
    elif any(p in nombre_lower for p in ["rtx", "rx", "gpu", "graphics card", "tarjeta de video"]):
        return 9
    elif any(p in nombre_lower for p in ["monitor", "display", "screen"]):
        return 10
    elif any(p in nombre_lower for p in ["ssd", "hdd", "nvme", "disco duro", "storage"]):
        return 11
    elif any(p in nombre_lower for p in ["ipad", "tab", "tablet"]):
        return 12
    return 1

def extraer_de_amazon(url_amazon: str):
    payload = {
        'api_key': SCRAPERAPI_KEY,
        'url': url_amazon,
        'country_code': 'us',
        'render': 'true'
    }
    response = requests.get('http://api.scraperapi.com', params=payload, timeout=30)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    titulo_elem = soup.find(id="productTitle")
    nombre = titulo_elem.get_text().strip() if titulo_elem else "Producto Amazon"

    precio = 0.0
    precio_elem = soup.find("span", class_="a-offscreen") or soup.find(id="priceblock_ourprice")
    if precio_elem:
        precio_texto = precio_elem.get_text().replace(',', '')
        match = re.search(r'\d+\.\d+|\d+', precio_texto)
        if match:
            precio = float(match.group())

    calificacion = "⭐ N/A"
    patron_rating = re.search(r'(\d[\.,]\d)\s*(out of 5 stars|de 5 estrellas|de 5)', response.text, re.IGNORECASE)
    if patron_rating:
        calificacion = f"⭐ {patron_rating.group(1).replace(',', '.')} / 5"

    especificaciones = {}
    tabla_specs = soup.find("table", class_="a-keyvalue") or soup.find(id="productDetails_techSpec_section_1")
    if tabla_specs:
        for fila in tabla_specs.find_all("tr"):
            k, v = fila.find("th"), fila.find("td")
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
# 4. RUTAS API
# ==========================================

@app.get("/api/sugerencias")
async def obtener_sugerencias(q: str = ""):
    texto = q.strip()
    if not texto or len(texto) < 2:
        return []
    try:
        res = supabase.table('productos').select('nombre').ilike('nombre', f"%{texto}%").limit(5).execute()
        if res.data:
            return list(set([item['nombre'] for item in res.data]))
    except Exception:
        pass
    return []

@app.post("/api/obtener-producto")
async def obtener_producto(req: SolicitudProducto):
    entrada = req.url_amazon.strip()

    try:
        # 1. Buscar primero en Supabase
        res = supabase.table('productos').select('*').ilike('nombre', f"%{entrada}%").limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]

        # 2. Si no está en Supabase y es una URL de Amazon, extraer
        if "amazon." in entrada:
            producto_datos = extraer_de_amazon(entrada)
            if not producto_datos:
                raise HTTPException(status_code=400, detail="No se pudo extraer la información del enlace.")
            supabase.table('productos').upsert(producto_datos, on_conflict='slug').execute()
            return producto_datos

        # 3. Intentar búsqueda automática en Amazon
        url_encontrada = buscar_url_en_amazon(entrada)
        if url_encontrada:
            producto_datos = extraer_de_amazon(url_encontrada)
            if producto_datos:
                supabase.table('productos').upsert(producto_datos, on_conflict='slug').execute()
                return producto_datos

        raise HTTPException(status_code=404, detail=f"No se encontró información para '{entrada}'.")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el servidor: {str(e)}")
