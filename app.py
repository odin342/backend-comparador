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
SCRAPERAPI_KEY = "TU_SCRAPERAPI_KEY_REAL"
SUPABASE_URL = "https://TU-PROYECTO-REAL.supabase.co"
SUPABASE_KEY = "TU_SERVICE_ROLE_O_ANON_KEY_REAL"

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
    categoria_id: int = 0  # 0 significa 'Todas las categorías'

# Nombres legibles de categorías
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

    html_text = response.text
    soup = BeautifulSoup(html_text, 'html.parser')

    # Nombre
    titulo_elem = soup.find(id="productTitle")
    nombre = titulo_elem.get_text().strip() if titulo_elem else "Producto Amazon"

    # Imagen URL
    imagen_url = ""
    img_elem = soup.find(id="landingImage") or soup.find(id="imgBlkFront")
    if img_elem:
        if img_elem.has_attr('data-old-hires') and img_elem['data-old-hires']:
            imagen_url = img_elem['data-old-hires']
        elif img_elem.has_attr('src'):
            imagen_url = img_elem['src']
            
    if not imagen_url:
        img_dynamic = soup.find("img", {"id": "landingImage"})
        if img_dynamic and img_dynamic.has_attr("data-a-dynamic-image"):
            try:
                imgs_dict = json.loads(img_dynamic["data-a-dynamic-image"])
                imagen_url = list(imgs_dict.keys())[0]
            except Exception:
                pass

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
        calificacion = f"⭐ {patron_rating.group(1).replace(',', '.')} / 5"

    # ESPECIFICACIONES TÉCNICAS (Búsqueda exhaustiva)
    especificaciones = {}

    # 1. Tablas de características técnicas
    for tr in soup.select("table.a-keyvalue tr, #productDetails_techSpec_section_1 tr, #technicalSpecifications_section_1 tr, .po-row"):
        th = tr.find(["th", "td"], class_=re.compile(r"a-span3|prodDetSectionEntry")) or tr.find("th")
        td = tr.find("td", class_=re.compile(r"a-span9|prodDetAttrValue")) or tr.find_all("td")[-1] if tr.find_all("td") else None
        if th and td:
            k = th.get_text().strip().replace('\u200e', '').replace('\n', '')
            v = td.get_text().strip().replace('\u200e', '').replace('\n', '')
            if k and v and len(k) < 60:
                especificaciones[k] = v

    # 2. Listas de viñetas de detalles (#detailBullets_feature_div)
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

    # EXTRAER AÑO DE LANZAMIENTO
    anio_lanzamiento = "Desconocido"

    # Revisa especificaciones recopiladas
    for k, v in especificaciones.items():
        if any(term in k.lower() for term in ["date first available", "model year", "fecha de disponibilidad", "año", "release"]):
            match = re.search(r'\b(201[5-9]|202[0-6])\b', v)
            if match:
                anio_lanzamiento = match.group(0)
                break

    # Si aún no aparece, escanea el HTML completo o el título
    if anio_lanzamiento == "Desconocido":
        match_html = re.search(r'(?:Date First Available|Fecha de primera disponibilidad)[^\d]+(201[5-9]|202[0-6])', html_text, re.IGNORECASE)
        if match_html:
            anio_lanzamiento = match_html.group(1)
        else:
            match_title = re.search(r'\b(201[5-9]|202[0-6])\b', nombre)
            if match_title:
                anio_lanzamiento = match_title.group(0)

    slug = re.sub(r'[^a-z0-9]+', '-', nombre.lower()).strip('-')[:50]
    cat_id = detectar_categoria_id(nombre, soup)

    return {
        "nombre": nombre[:100],
        "slug": slug,
        "precio": precio,
        "calificacion": calificacion,
        "categoria_id": cat_id,
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

        # 1. Si es URL de Amazon
        if "amazon." in entrada:
            producto_datos = extraer_de_amazon(entrada)
        else:
            # 2. Buscar en Supabase
            q_supa = supabase.table('productos').select('*').ilike('nombre', f"%{entrada}%")
            if cat_filtro > 0:
                q_supa = q_supa.eq('categoria_id', cat_filtro)
            res = q_supa.limit(1).execute()

            if res.data and len(res.data) > 0:
                producto_datos = res.data[0]
            else:
                # 3. Buscar automáticamente en Amazon
                url_encontrada = buscar_url_en_amazon(entrada)
                if url_encontrada:
                    producto_datos = extraer_de_amazon(url_encontrada)

        if not producto_datos:
            raise HTTPException(status_code=404, detail=f"No se encontró información para '{entrada}'.")

        # --- VALIDACIÓN STRICTA DE CATEGORÍA ---
        if cat_filtro > 0 and producto_datos.get("categoria_id") != cat_filtro:
            nombre_cat_esperada = NOMBRES_CATEGORIAS.get(cat_filtro, "seleccionada")
            nombre_cat_detectada = NOMBRES_CATEGORIAS.get(producto_datos.get("categoria_id"), "otra categoría")
            raise HTTPException(
                status_code=400,
                detail=f"El producto '{producto_datos.get('nombre')}' pertenece a '{nombre_cat_detectada}', pero seleccionaste el filtro '{nombre_cat_esperada}'."
            )

        # Guardar / Actualizar en Supabase si es extracción nueva
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
