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
SCRAPERAPI_KEY = "ffed8880e2e45f1789bd6e0379c65b0b"
SUPABASE_URL = "https://jqvodxitphzyuizfhkyj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Impxdm9keGl0cGh6eXVpemZoa3lqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODQzOTM4MCwiZXhwIjoyMTA0MDE1MzgwfQ.zV-wfwvVP-6mHONEs7K1tW6c8CbZG6jW-nvy5HZPpjM"

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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detalle": "Error interno en el servidor", "error": str(exc)}
    )

class SolicitudProducto(BaseModel):
    url_amazon: str
    categoria_id: int = 0

NOMBRES_CATEGORIAS = {
    1: "Celulares", 2: "Mouses", 3: "Teclados", 4: "Televisores",
    5: "Portátiles", 6: "Diademas", 7: "Board", 8: "Ram",
    9: "Tarjeta De Video", 10: "Monitores", 11: "Disco Duro", 12: "Tablet"
}

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

def detectar_categoria_id(nombre_producto: str) -> int:
    nombre_lower = nombre_producto.lower()
    if any(p in nombre_lower for p in ["phone", "celular", "smartphone", "iphone", "galaxy", "xiaomi"]):
        return 1
    elif any(p in nombre_lower for p in ["mouse", "ratón", "trackball"]):
        return 2
    elif any(p in nombre_lower for p in ["keyboard", "teclado", "keypad", "g213", "g515"]):
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

    html_text = response.text
    soup = BeautifulSoup(html_text, 'html.parser')

    titulo_elem = soup.find(id="productTitle")
    nombre = titulo_elem.get_text().strip() if titulo_elem else "Producto Amazon"

    imagen_url = ""
    img_elem = soup.find(id="landingImage") or soup.find(id="imgBlkFront")
    if img_elem:
        if img_elem.has_attr('data-old-hires') and img_elem['data-old-hires']:
            imagen_url = img_elem['data-old-hires']
        elif img_elem.has_attr('src'):
            imagen_url = img_elem['src']

    precio = 0.0
    precio_elem = soup.find("span", class_="a-offscreen") or soup.find(id="priceblock_ourprice")
    if precio_elem:
        precio_texto = precio_elem.get_text().replace(',', '')
        match = re.search(r'\d+\.\d+|\d+', precio_texto)
        if match:
            precio = float(match.group())

    calificacion = "⭐ N/A"
    patron_rating = re.search(r'(\d[\.,]\d)\s*(out of 5 stars|de 5 estrellas|de 5)', html_text, re.IGNORECASE)
    if patron_rating:
        calificacion = f"⭐ {patron_rating.group(1).replace(',', '.')} / 5"

    especificaciones = {}
    for tr in soup.select("table.a-keyvalue tr, #productDetails_techSpec_section_1 tr, #technicalSpecifications_section_1 tr, .po-row"):
        th = tr.find(["th", "td"], class_=re.compile(r"a-span3|prodDetSectionEntry")) or tr.find("th")
        td = tr.find("td", class_=re.compile(r"a-span9|prodDetAttrValue")) or tr.find_all("td")[-1] if tr.find_all("td") else None
        if th and td:
            k = th.get_text().strip().replace('\u200e', '').replace('\n', '')
            v = td.get_text().strip().replace('\u200e', '').replace('\n', '')
            if k and v and len(k) < 60:
                especificaciones[k] = v

    for li in soup.select("#detailBullets_feature_div li, #productDetails_db_sections li"):
        spans = li.find_all("span", class_="a-list-item")
        if spans:
            texto = spans[0].get_text()
            if ":" in texto:
                partes = texto.split(":", 1)
                k = re.sub(r'\s+', ' ', partes[0]).strip().replace('\u200e', '')
                v = re.sub(r'\s+', ' ', partes[1]).strip().replace('\u200e', '')
                if k and v and len(k) < 60:
                    especificaciones[k] = v

    # --- EXTRAER AÑO DE LANZAMIENTO (Búsqueda por patrones avanzados) ---
    anio_lanzamiento = "Desconocido"

    # A. Buscar en el diccionario de especificaciones recopilado
    for k, v in especificaciones.items():
        k_lower = k.lower()
        if any(term in k_lower for term in ["date first available", "model year", "fecha de disponibilidad", "primera disponibilidad", "año", "release"]):
            match = re.search(r'\b(201[0-9]|202[0-6])\b', v)
            if match:
                anio_lanzamiento = match.group(0)
                break

    # B. Buscar en el texto HTML global de Amazon
    if anio_lanzamiento == "Desconocido":
        patron_fecha = re.search(r'(?:Date First Available|Fecha de primera disponibilidad|Model Year)[^\d]{1,50}(?:[A-Za-z]+|\d{1,2})[,\s\.\-]+(?:[A-Za-z]+|\d{1,2})[,\s\.\-]+(201[0-9]|202[0-6])', html_text, re.IGNORECASE)
        if patron_fecha:
            anio_lanzamiento = patron_fecha.group(1)

    # C. Buscar cualquier año de 4 dígitos (2010 a 2026) en el título del producto como último recurso
    if anio_lanzamiento == "Desconocido":
        match_titulo = re.search(r'\b(201[0-9]|202[0-6])\b', nombre)
        if match_titulo:
            anio_lanzamiento = match_titulo.group(0)

    slug = re.sub(r'[^a-z0-9]+', '-', nombre.lower()).strip('-')[:50]

    return {
        "nombre": nombre[:100],
        "slug": slug,
        "precio": precio,
        "calificacion": calificacion,
        "categoria_id": detectar_categoria_id(nombre),
        "imagen_url": imagen_url,
        "anio_lanzamiento": anio_lanzamiento,
        "especificaciones": especificaciones
    }

# ==========================================
# 4. RUTAS API
# ==========================================

@app.get("/api/sugerencias")
async def obtener_sugerencias(q: str = "", categoria_id: int = 0):
    texto = q.strip()
    if not texto or len(texto) < 2:
        return []
    try:
        query = supabase.table('productos').select('nombre').ilike('nombre', f"%{texto}%")
        if categoria_id > 0:
            query = query.eq('categoria_id', categoria_id)
            
        res = query.limit(5).execute()
        if res.data:
            return list(set([item['nombre'] for item in res.data]))
    except Exception:
        pass
    return []

@app.post("/api/obtener-producto")
async def obtener_producto(req: SolicitudProducto):
    entrada = req.url_amazon.strip()
    cat_filtro = req.categoria_id

    try:
        producto_datos = None

        if "amazon." in entrada:
            producto_datos = extraer_de_amazon(entrada)
        else:
            q_supa = supabase.table('productos').select('*').ilike('nombre', f"%{entrada}%")
            if cat_filtro > 0:
                q_supa = q_supa.eq('categoria_id', cat_filtro)
            res = q_supa.limit(1).execute()

            # Si el producto está en Supabase Y tiene el año cargado, lo usa
            if res.data and len(res.data) > 0 and res.data[0].get("anio_lanzamiento") and res.data[0].get("anio_lanzamiento") != "Desconocido":
                producto_datos = res.data[0]
            else:
                # Si no está o no tiene año, lo busca de nuevo en Amazon
                url_encontrada = buscar_url_en_amazon(entrada)
                if url_encontrada:
                    producto_datos = extraer_de_amazon(url_encontrada)
                elif res.data and len(res.data) > 0:
                    producto_datos = res.data[0]

        if not producto_datos:
            raise HTTPException(status_code=404, detail=f"No se encontró información para '{entrada}'.")

        # Validación estricta de categoría
        if cat_filtro > 0 and producto_datos.get("categoria_id") != cat_filtro:
            nombre_cat_esperada = NOMBRES_CATEGORIAS.get(cat_filtro, "seleccionada")
            nombre_cat_detectada = NOMBRES_CATEGORIAS.get(producto_datos.get("categoria_id"), "otra categoría")
            raise HTTPException(
                status_code=400,
                detail=f"El producto pertenece a '{nombre_cat_detectada}', pero seleccionaste la categoría '{nombre_cat_esperada}'."
            )

        if "slug" in producto_datos:
            try:
                supabase.table('productos').upsert(producto_datos, on_conflict='slug').execute()
            except Exception:
                pass

        return producto_datos

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el servidor: {str(e)}")
