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
RAPI_KEY = "ffed8880e2e45f1789bd6e0379c65b0b"
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
    tienda: str = "auto"  # 'auto', 'mercadolibre', 'amazon'
    pais_ml: str = "MCO"  # 'MCO' (Colombia), 'MLM' (México), 'MLA' (Argentina), etc.

NOMBRES_CATEGORIAS = {
    1: "Celulares", 2: "Mouses", 3: "Teclados", 4: "Televisores",
    5: "Portátiles", 6: "Diademas", 7: "Board", 8: "Ram",
    9: "Tarjeta De Video", 10: "Monitores", 11: "Disco Duro", 12: "Tablet"
}

# ==========================================
# 3. EXTRACCIÓN MERCADOLIBRE (API OFICIAL)
# ==========================================

def extraer_de_mercadolibre(busqueda: str, site_id: str = "MCO"):
    url_api = f"https://api.mercadolibre.com/sites/{site_id}/search?q={quote_plus(busqueda)}&limit=1"
    
    # AGREGAR USER-AGENT PARA EVITAR BLOQUEO DE MERCADOLIBRE EN RENDER
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url_api, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                item = results[0]
                
                # Imagen de alta calidad
                imagen_url = item.get("thumbnail", "").replace("-I.jpg", "-O.jpg")
                
                # Especificaciones desde atributos
                especificaciones = {}
                for attr in item.get("attributes", []):
                    nombre_attr = attr.get("name")
                    val_attr = attr.get("value_name")
                    if nombre_attr and val_attr and len(nombre_attr) < 50:
                        especificaciones[nombre_attr] = val_attr

                nombre = item.get("title", "Producto MercadoLibre")
                precio = float(item.get("price", 0.0))
                
                # Conversión de moneda local a USD base
                precio_usd = precio
                if site_id == "MCO":
                    precio_usd = round(precio / 4000.0, 2)
                elif site_id == "MLM":
                    precio_usd = round(precio / 18.0, 2)

                slug = re.sub(r'[^a-z0-9]+', '-', nombre.lower()).strip('-')[:50]

                return {
                    "nombre": nombre[:100],
                    "slug": f"ml-{slug}",
                    "precio": precio_usd,
                    "precio_local": precio,
                    "moneda_local": item.get("currency_id", "COP"),
                    "calificacion": "⭐ 4.7 / 5",
                    "categoria_id": detectar_categoria_id(nombre),
                    "imagen_url": imagen_url,
                    "especificaciones": especificaciones,
                    "tienda": "MercadoLibre",
                    "url_compra": item.get("permalink", "")
                }
    except Exception:
        pass
    return None

# ==========================================
# 4. EXTRACCIÓN AMAZON
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
    if any(p in nombre_lower for p in ["phone", "celular", "smartphone", "iphone", "galaxy", "xiaomi", "redmi"]):
        return 1
    elif any(p in nombre_lower for p in ["mouse", "ratón", "trackball"]):
        return 2
    elif any(p in nombre_lower for p in ["keyboard", "teclado", "keypad", "g213", "g515", "k556", "redragon"]):
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
    return 3  # Por defecto si no coincide, retoma la categoría actual

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

    slug = re.sub(r'[^a-z0-9]+', '-', nombre.lower()).strip('-')[:50]

    return {
        "nombre": nombre[:100],
        "slug": f"az-{slug}",
        "precio": precio,
        "calificacion": calificacion,
        "categoria_id": detectar_categoria_id(nombre),
        "imagen_url": imagen_url,
        "especificaciones": especificaciones,
        "tienda": "Amazon",
        "url_compra": url_amazon
    }

# ==========================================
# 5. RUTAS API
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
    tienda_pref = req.tienda.lower()
    pais_ml = req.pais_ml.upper()

    try:
        producto_datos = None

        # 1. Si es enlace directo de Amazon
        if "amazon." in entrada:
            producto_datos = extraer_de_amazon(entrada)

        # 2. Si se prefiere MercadoLibre
        elif tienda_pref == "mercadolibre":
            producto_datos = extraer_de_mercadolibre(entrada, site_id=pais_ml)

        # 3. Si es Automático (Busca primero en MercadoLibre por velocidad, luego Supabase/Amazon)
        else:
            # A. Intentar MercadoLibre
            producto_datos = extraer_de_mercadolibre(entrada, site_id=pais_ml)
            
            # B. Intentar en Supabase
            if not producto_datos:
                q_supa = supabase.table('productos').select('*').ilike('nombre', f"%{entrada}%")
                if cat_filtro > 0:
                    q_supa = q_supa.eq('categoria_id', cat_filtro)
                res = q_supa.limit(1).execute()
                if res.data and len(res.data) > 0:
                    producto_datos = res.data[0]

            # C. Intentar Amazon si los anteriores no trajeron nada
            if not producto_datos:
                url_encontrada = buscar_url_en_amazon(entrada)
                if url_encontrada:
                    producto_datos = extraer_de_amazon(url_encontrada)

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

        # Guardar en Supabase
        if "slug" in producto_datos:
            try:
                # Filtrar solo campos válidos
                datos_guardar = {
                    "nombre": producto_datos.get("nombre"),
                    "slug": producto_datos.get("slug"),
                    "precio": producto_datos.get("precio"),
                    "calificacion": producto_datos.get("calificacion"),
                    "categoria_id": producto_datos.get("categoria_id"),
                    "imagen_url": producto_datos.get("imagen_url"),
                    "especificaciones": producto_datos.get("especificaciones")
                }
                supabase.table('productos').upsert(datos_guardar, on_conflict='slug').execute()
            except Exception:
                pass

        return producto_datos

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el servidor: {str(e)}")
