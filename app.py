# ==============================================================================
#  ORIGEN AVICOR — app.py
#  Backend Flask principal
#  "Crecimiento natural, sabor de verdad"
#
#  Estructura:
#    - Configuración y extensiones
#    - Modelos en memoria (preparados para BD)
#    - Decoradores / helpers de autenticación
#    - Rutas públicas:   /  /productos  /nosotros
#    - Ruta chatbot:     /chatbot
#    - Rutas de sesión:  /login  /logout  /registro
#    - API REST (JSON):  /api/*
#    - Manejadores de error
# ==============================================================================

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    abort,
    g,
)
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import os
import logging
import json
import re


# ==============================================================================
#  1. INICIALIZACIÓN DE LA APLICACIÓN
# ==============================================================================

app = Flask(
    __name__,
    template_folder="templates",   # carpeta donde viven los .html
    static_folder="static",        # carpeta de assets (css, js, img)
)


# ==============================================================================
#  2. CONFIGURACIÓN
#  En producción estas variables deben venir de variables de entorno (.env)
# ==============================================================================

app.config.update(
    # Clave secreta para firmar las cookies de sesión.
    # IMPORTANTE: cambiar por una cadena aleatoria larga en producción.
    SECRET_KEY=os.environ.get("SECRET_KEY", "avicor-dev-secret-cambia-en-produccion"),

    # Tiempo de vida de la sesión: 30 minutos de inactividad
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),

    # La sesión se marca como permanente por defecto (respeta el timeout)
    SESSION_PERMANENT=True,

    # Cookie de sesión solo se envía por HTTPS en producción
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",

    # La cookie no es accesible desde JavaScript (protección XSS)
    SESSION_COOKIE_HTTPONLY=True,

    # SameSite strict para protección CSRF básica
    SESSION_COOKIE_SAMESITE="Lax",

    # Nombre de la aplicación (usado en plantillas)
    APP_NAME="Origen Avicor",
    APP_SLOGAN="Crecimiento natural, sabor de verdad",
    APP_VERSION="1.0.0",

    # Número máximo de mensajes en el historial del chatbot por sesión
    CHATBOT_MAX_HISTORY=50,

    # Modo debug (sobreescribible con variable de entorno)
    DEBUG=os.environ.get("FLASK_DEBUG", "true").lower() == "true",
)


# ==============================================================================
#  3. LOGGING
# ==============================================================================

logging.basicConfig(
    level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("avicor")


# ==============================================================================
#  4. DATOS EN MEMORIA
#  Simulan una base de datos mientras se integra SQLAlchemy / PostgreSQL.
#  Cada "tabla" es un dict keyed por id.
# ==============================================================================

# ---- Usuarios ----------------------------------------------------------------
#  Contraseñas almacenadas como SHA-256 hex (solo para demo).
#  En producción usar bcrypt / argon2 y una BD real.
_usuarios = {
    1: {
        "id": 1,
        "nombre": "Admin Avicor",
        "email": "admin@origenavicor.bo",
        "password_hash": hashlib.sha256(b"admin1234").hexdigest(),
        "rol": "admin",
        "activo": True,
        "creado_en": datetime(2024, 1, 1),
    },
    2: {
        "id": 2,
        "nombre": "Cliente Demo",
        "email": "cliente@demo.bo",
        "password_hash": hashlib.sha256(b"cliente123").hexdigest(),
        "rol": "cliente",
        "activo": True,
        "creado_en": datetime(2024, 6, 15),
    },
}
_siguiente_usuario_id = 3  # auto-increment simulado


# ---- Productos ---------------------------------------------------------------
_productos = [
    {
        "id": 1,
        "nombre": "Pollo entero Avicor",
        "categoria": "entero",
        "descripcion": (
            "Pollo criollo completo, criado en libertad. "
            "Peso promedio 2.2 kg. Ideal para horno, parrilla o caldo."
        ),
        "precio": 65.00,
        "precio_original": None,
        "unidad": "unidad",
        "imagen": "pollo-entero.jpg",
        "badge": "Más popular",
        "badge_color": "verde",
        "rating": 4.9,
        "reseñas": 148,
        "atributos": ["Sin hormonas", "~2.2 kg", "Fresco"],
        "disponible": True,
    },
    {
        "id": 2,
        "nombre": "Pechuga fileteada",
        "categoria": "pechuga",
        "descripcion": (
            "Filetes de pechuga sin hueso y sin piel. "
            "Proteína pura y natural. 500 g en empaque al vacío."
        ),
        "precio": 48.00,
        "precio_original": None,
        "unidad": "500 g",
        "imagen": "pechuga-fileteada.jpg",
        "badge": "Premium",
        "badge_color": "naranja",
        "rating": 4.8,
        "reseñas": 93,
        "atributos": ["Alta proteína", "500 g", "Al vacío"],
        "disponible": True,
    },
    {
        "id": 3,
        "nombre": "Pack Familiar Completo",
        "categoria": "pack",
        "descripcion": (
            "1 pollo entero + 1 kg de pechugas + ½ kg de muslos. "
            "La solución perfecta para la semana. Ahorrás 15%."
        ),
        "precio": 145.00,
        "precio_original": 170.00,
        "unidad": "pack",
        "imagen": "pack-familiar.jpg",
        "badge": "Más vendido · -15%",
        "badge_color": "marron",
        "rating": 4.9,
        "reseñas": 201,
        "atributos": ["1 pollo entero", "1 kg pechugas", "½ kg muslos"],
        "disponible": True,
    },
    {
        "id": 4,
        "nombre": "Muslos sazonados",
        "categoria": "muslos",
        "descripcion": (
            "Muslos tiernos con marinado natural de hierbas del campo. "
            "Listos para el horno o la sartén. Pack de 4 unidades."
        ),
        "precio": 38.00,
        "precio_original": None,
        "unidad": "pack x4",
        "imagen": "muslos-sazonados.jpg",
        "badge": "Nuevo",
        "badge_color": "verde",
        "rating": 4.7,
        "reseñas": 57,
        "atributos": ["Marinado natural", "4 unidades"],
        "disponible": True,
    },
    {
        "id": 5,
        "nombre": "Piernas con hueso",
        "categoria": "muslos",
        "descripcion": (
            "Piernas de pollo criollo con hueso. Ideales para sopas, "
            "caldos o al horno. Pack de 500 g."
        ),
        "precio": 32.00,
        "precio_original": 38.00,
        "unidad": "500 g",
        "imagen": "piernas-hueso.jpg",
        "badge": None,
        "badge_color": None,
        "rating": 4.6,
        "reseñas": 44,
        "atributos": ["Con hueso", "500 g"],
        "disponible": True,
    },
    {
        "id": 6,
        "nombre": "Pollo orgánico certificado",
        "categoria": "entero",
        "descripcion": (
            "Crianza orgánica certificada con sello de trazabilidad QR. "
            "El producto bandera de Avicor. Peso aprox. 2.5 kg."
        ),
        "precio": 80.00,
        "precio_original": None,
        "unidad": "unidad",
        "imagen": "pollo-organico.jpg",
        "badge": "Orgánico",
        "badge_color": "verde",
        "rating": 5.0,
        "reseñas": 72,
        "atributos": ["Certificado", "QR trazable", "~2.5 kg"],
        "disponible": True,
    },
    {
        "id": 7,
        "nombre": "Menudencias mix",
        "categoria": "menudencias",
        "descripcion": (
            "Combinado de mollejas, corazones e hígados frescos. "
            "Ideal para caldo concentrado o frituras. 300 g."
        ),
        "precio": 18.00,
        "precio_original": 24.00,
        "unidad": "300 g",
        "imagen": "menudencias-mix.jpg",
        "badge": "Oferta",
        "badge_color": "oferta",
        "rating": 4.5,
        "reseñas": 31,
        "atributos": ["Para caldo", "300 g"],
        "disponible": True,
    },
    {
        "id": 8,
        "nombre": "Pack Parrillero",
        "categoria": "pack",
        "descripcion": (
            "Muslos, piernas y alitas marinadas con hierbas del campo. "
            "Para 4 a 6 personas. Perfecto para el asado del fin de semana."
        ),
        "precio": 115.00,
        "precio_original": 135.00,
        "unidad": "pack",
        "imagen": "pack-parrillero.jpg",
        "badge": "Pack especial",
        "badge_color": "marron",
        "rating": 4.9,
        "reseñas": 61,
        "atributos": ["Para parrilla", "4-6 personas", "Marinado"],
        "disponible": True,
    },
]

# ---- Categorías --------------------------------------------------------------
CATEGORIAS = {
    "todos":       "Todos",
    "entero":      "Pollo entero",
    "pechuga":     "Pechugas",
    "muslos":      "Muslos y piernas",
    "pack":        "Packs y combos",
    "menudencias": "Menudencias",
}

# ---- Testimonios (también usados en el index) --------------------------------
_testimonios = [
    {
        "id": 1,
        "nombre": "María Laura C.",
        "lugar": "Miraflores, La Paz",
        "texto": (
            "La diferencia de sabor es brutal. Mi familia entera notó el cambio "
            "desde el primer plato. El caldo que sale de este pollo es completamente "
            "diferente a lo que compraba antes en el supermercado."
        ),
        "rating": 5,
        "avatar": "avatar-maria.jpg",
        "destacado": False,
    },
    {
        "id": 2,
        "nombre": "Roberto Mamani",
        "lugar": "Chef · Sopocachi, La Paz",
        "texto": (
            "Soy cocinero y sé cuando un ingrediente es de calidad real. "
            "Este pollo tiene textura, tiene sabor, tiene personalidad. "
            "Origen Avicor es lo que Bolivia necesitaba hace mucho tiempo."
        ),
        "rating": 5,
        "avatar": "avatar-roberto.jpg",
        "destacado": True,
    },
    {
        "id": 3,
        "nombre": "Ana Solís",
        "lugar": "Calacoto, La Paz",
        "texto": (
            "El servicio de entrega es impecable. Llega frío, bien empacado "
            "y con toda la información de trazabilidad. El QR es un detalle genial."
        ),
        "rating": 5,
        "avatar": "avatar-ana.jpg",
        "destacado": False,
    },
]

# ---- Pedidos (simulados, en producción van a BD) ----------------------------
_pedidos = []
_siguiente_pedido_id = 1001


# ==============================================================================
#  5. HELPERS DE AUTENTICACIÓN
# ==============================================================================

def _hash_password(password: str) -> str:
    """Devuelve el hash SHA-256 de la contraseña en texto plano.
    En producción reemplazar con bcrypt.hashpw()."""
    return hashlib.sha256(password.encode()).hexdigest()


def _verificar_password(password: str, hash_almacenado: str) -> bool:
    """Compara la contraseña en texto plano contra el hash almacenado."""
    return _hash_password(password) == hash_almacenado


def _buscar_usuario_por_email(email: str) -> dict | None:
    """Retorna el usuario cuyo email coincide, o None si no existe."""
    email_lower = email.strip().lower()
    for usuario in _usuarios.values():
        if usuario["email"].lower() == email_lower:
            return usuario
    return None


def _buscar_usuario_por_id(user_id: int) -> dict | None:
    """Retorna el usuario por su ID, o None."""
    return _usuarios.get(int(user_id))


def login_requerido(f):
    """Decorador: redirige a /login si el usuario no está autenticado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Necesitás iniciar sesión para acceder a esa página.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_requerido(f):
    """Decorador: solo permite acceso a usuarios con rol 'admin'."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Acceso restringido. Iniciá sesión.", "warning")
            return redirect(url_for("login", next=request.url))
        usuario = _buscar_usuario_por_id(session["usuario_id"])
        if not usuario or usuario.get("rol") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ==============================================================================
#  6. CONTEXTO GLOBAL PARA PLANTILLAS
#  Disponible en todos los Jinja2 templates como {{ usuario_actual }}, etc.
# ==============================================================================

@app.before_request
def cargar_usuario_actual():
    """Inyecta el usuario autenticado en `g` antes de cada petición."""
    g.usuario_actual = None
    if "usuario_id" in session:
        g.usuario_actual = _buscar_usuario_por_id(session["usuario_id"])
        # Si el usuario fue borrado/desactivado invalidamos la sesión
        if g.usuario_actual is None or not g.usuario_actual.get("activo"):
            session.clear()
            g.usuario_actual = None


@app.context_processor
def inyectar_contexto_global():
    """Variables disponibles en todos los templates sin pasarlas explícitamente."""
    return {
        "app_nombre":   app.config["APP_NAME"],
        "app_slogan":   app.config["APP_SLOGAN"],
        "anio_actual":  datetime.now().year,
        "usuario":      g.get("usuario_actual"),
        "es_admin":     (g.get("usuario_actual") or {}).get("rol") == "admin",
        "categorias":   CATEGORIAS,
    }


# ==============================================================================
#  7. RUTAS PÚBLICAS — Páginas principales
# ==============================================================================

# ------------------------------------------------------------------------------
#  7.1  /  — Página de inicio (index.html)
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    """
    Página de inicio de Origen Avicor.
    Muestra los productos destacados y testimonios recientes.
    """
    # Productos destacados: los 3 con mayor rating
    destacados = sorted(
        [p for p in _productos if p["disponible"]],
        key=lambda p: p["rating"],
        reverse=True,
    )[:3]

    # Testimonios: primero el destacado, luego los demás
    testimonios_ordenados = sorted(
        _testimonios,
        key=lambda t: (t["destacado"], t["rating"]),
        reverse=True,
    )

    logger.debug("GET / — usuario: %s", g.usuario_actual)

    return render_template(
        "index.html",
        productos_destacados=destacados,
        testimonios=testimonios_ordenados,
    )


# ------------------------------------------------------------------------------
#  7.2  /productos  — Catálogo completo con filtros
# ------------------------------------------------------------------------------
@app.route("/productos")
def productos():
    """
    Catálogo de productos con soporte para:
      ?categoria=<slug>   — filtra por categoría
      ?q=<texto>          — búsqueda por nombre/descripción
      ?orden=<criterio>   — precio_asc | precio_desc | rating | nombre
      ?min=<int>          — precio mínimo en Bs.
      ?max=<int>          — precio máximo en Bs.
    """
    # ---- Leer parámetros de consulta ----------------------------------------
    categoria_sel = request.args.get("categoria", "todos").strip().lower()
    busqueda      = request.args.get("q", "").strip().lower()
    orden         = request.args.get("orden", "relevancia").strip()
    precio_min    = _parsear_int(request.args.get("min"), default=0)
    precio_max    = _parsear_int(request.args.get("max"), default=99999)

    # ---- Validar categoría ---------------------------------------------------
    if categoria_sel not in CATEGORIAS:
        categoria_sel = "todos"

    # ---- Filtrar productos ---------------------------------------------------
    resultado = [p for p in _productos if p["disponible"]]

    if categoria_sel != "todos":
        resultado = [p for p in resultado if p["categoria"] == categoria_sel]

    if busqueda:
        resultado = [
            p for p in resultado
            if busqueda in p["nombre"].lower()
            or busqueda in p["descripcion"].lower()
            or busqueda in p["categoria"].lower()
        ]

    resultado = [
        p for p in resultado
        if precio_min <= p["precio"] <= precio_max
    ]

    # ---- Ordenar -------------------------------------------------------------
    criterios_orden = {
        "precio_asc":  lambda p: p["precio"],
        "precio_desc": lambda p: -p["precio"],
        "rating":      lambda p: -p["rating"],
        "nombre":      lambda p: p["nombre"].lower(),
    }
    if orden in criterios_orden:
        resultado = sorted(resultado, key=criterios_orden[orden])

    logger.debug(
        "GET /productos — categoría=%s  búsqueda=%s  orden=%s  resultados=%d",
        categoria_sel, busqueda or "—", orden, len(resultado),
    )

    return render_template(
        "productos.html",
        productos=resultado,
        total_resultados=len(resultado),
        categoria_seleccionada=categoria_sel,
        busqueda=busqueda,
        orden_seleccionado=orden,
        precio_min=precio_min,
        precio_max=precio_max if precio_max < 99999 else 300,
    )


# ------------------------------------------------------------------------------
#  7.3  /nosotros  — Página "Sobre nosotros"
# ------------------------------------------------------------------------------
@app.route("/nosotros")
def nosotros():
    """
    Historia, origen en Coroico, misión, visión y valores.
    """
    # Hitos cronológicos de la empresa
    hitos = [
        {
            "anio": 2015,
            "titulo": "El primer gallinero",
            "texto": (
                "Don Efraín amplía el gallinero familiar a 200 aves con técnicas "
                "heredadas de su padre. Sin hormonas, sin jaulas."
            ),
            "icono": "🌱",
        },
        {
            "anio": 2017,
            "titulo": "La alianza familiar",
            "texto": (
                "Marco Quispe regresa de La Paz con una visión clara. "
                "Se suman tres familias vecinas de Coroico."
            ),
            "icono": "🤝",
        },
        {
            "anio": 2018,
            "titulo": "Primeras entregas en La Paz",
            "texto": (
                "Con una camioneta y un cuaderno de pedidos, Avicor comienza "
                "sus primeras entregas regulares en Sopocachi y Miraflores."
            ),
            "icono": "🚚",
        },
        {
            "anio": 2020,
            "titulo": "Empaque sustentable y trazabilidad QR",
            "texto": (
                "Se implementa empaque biodegradable al vacío con código QR. "
                "Los clientes conocen el origen exacto de su producto."
            ),
            "icono": "📦",
        },
        {
            "anio": 2021,
            "titulo": "Red de 12 familias productoras",
            "texto": (
                "Avicor formaliza su red: 12 familias de Coroico y los Yungas "
                "trabajan bajo el Protocolo Avicor con precio justo garantizado."
            ),
            "icono": "🌐",
        },
        {
            "anio": 2024,
            "titulo": "300+ familias, una sola convicción",
            "texto": (
                "Más de 300 familias bolivianas reciben Avicor regularmente. "
                "Valoración promedio: 4.9 sobre 5."
            ),
            "icono": "⭐",
        },
    ]

    valores = [
        {"icono": "🌿", "titulo": "Naturalidad",      "texto": "Si no es natural, no es Avicor."},
        {"icono": "🤝", "titulo": "Comercio justo",   "texto": "Pagamos el precio que los productores merecen."},
        {"icono": "🔍", "titulo": "Transparencia",     "texto": "Trazabilidad completa en cada producto."},
        {"icono": "🐔", "titulo": "Bienestar animal",  "texto": "Las aves tienen espacio, sol y dignidad."},
        {"icono": "🌍", "titulo": "Sostenibilidad",    "texto": "Empaques biodegradables y agua de vertiente."},
        {"icono": "🏠", "titulo": "Comunidad local",   "texto": "100% producción con familias de Coroico."},
        {"icono": "🎯", "titulo": "Excelencia",        "texto": "Rechazamos la mediocridad en cada paso."},
        {"icono": "💪", "titulo": "Orgullo boliviano", "texto": "Bolivia tiene una riqueza natural incomparable."},
    ]

    equipo = [
        {
            "nombre": "Efraín Quispe",
            "rol":    "Fundador",
            "lugar":  "Coroico, La Paz",
            "bio":    "40 años criando pollos en los Yungas. La sabiduría y el corazón de Avicor.",
            "avatar": "avatar-efrain.jpg",
        },
        {
            "nombre": "Marco Quispe",
            "rol":    "Co-fundador",
            "lugar":  "La Paz / Coroico",
            "bio":    "Hijo de Efraín. Conecta el campo con la ciudad y garantiza la cadena de frío.",
            "avatar": "avatar-marco.jpg",
        },
        {
            "nombre": "Rosario Mamani",
            "rol":    "Productora asociada",
            "lugar":  "Coroico, La Paz",
            "bio":    "Granjera desde 2017. Especialista en gallinas de raza criolla.",
            "avatar": "avatar-rosario.jpg",
        },
        {
            "nombre": "Luis Condori",
            "rol":    "Logística",
            "lugar":  "La Paz",
            "bio":    "Responsable de que cada pedido llegue frío, puntual y perfecto.",
            "avatar": "avatar-luis.jpg",
        },
    ]

    logger.debug("GET /nosotros")

    return render_template(
        "nosotros.html",
        hitos=hitos,
        valores=valores,
        equipo=equipo,
    )


# ------------------------------------------------------------------------------
#  7.4  /chatbot  — Interfaz del chatbot Avicor
# ------------------------------------------------------------------------------
@app.route("/chatbot")
def chatbot():
    """
    Interfaz del chatbot de Origen Avicor.
    El historial de conversación se almacena en la sesión del usuario.
    Requiere que la sesión esté activa (aunque no requiere login).
    """
    # Inicializar historial de chat en sesión si no existe
    if "chat_historial" not in session:
        session["chat_historial"] = []
        session["chat_iniciado_en"] = datetime.now().isoformat()

    historial = session.get("chat_historial", [])

    # Limitar historial al máximo configurado
    max_hist = app.config["CHATBOT_MAX_HISTORY"]
    if len(historial) > max_hist:
        historial = historial[-max_hist:]
        session["chat_historial"] = historial

    logger.debug(
        "GET /chatbot — sesión: %s  mensajes en historial: %d",
        session.get("_id", "anónima"), len(historial),
    )

    return render_template(
        "chatbot.html",
        historial=historial,
        productos_rapidos=_productos[:4],  # acceso rápido desde el chat
    )
@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json()
        mensaje_usuario = data.get("message")
        
        import chatbot as modulo_bot
        # Aquí asumimos que tu archivo chatbot.py tiene una función llamada obtener_respuesta
        respuesta = modulo_bot.obtener_respuesta(mensaje_usuario)
        
        return jsonify({"reply": respuesta})
    except Exception as e:
        return jsonify({"reply": "Lo siento, tuve un error interno."}), 500
# ==============================================================================
#  8. RUTAS DE AUTENTICACIÓN
# ==============================================================================

# ------------------------------------------------------------------------------
#  8.1  /login  — Iniciar sesión
# ------------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    GET:  Muestra el formulario de login.
    POST: Valida credenciales y crea la sesión.
    """
    # Si ya está autenticado, redirigir a inicio
    if "usuario_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        recordar = request.form.get("recordar") == "on"

        # ---- Validación básica de formato ------------------------------------
        if not email or not password:
            flash("Por favor completá todos los campos.", "error")
            return redirect(url_for("login"))

        if not _email_valido(email):
            flash("El formato del correo no es válido.", "error")
            return redirect(url_for("login"))

        # ---- Buscar usuario en "BD" ------------------------------------------
        usuario = _buscar_usuario_por_email(email)

        if usuario is None or not _verificar_password(password, usuario["password_hash"]):
            # Mensaje genérico para no revelar si el email existe
            flash("Correo o contraseña incorrectos. Intentá de nuevo.", "error")
            logger.warning("Intento de login fallido para email: %s", email)
            return redirect(url_for("login"))

        if not usuario["activo"]:
            flash("Tu cuenta está desactivada. Contactá con soporte.", "error")
            return redirect(url_for("login"))

        # ---- Crear sesión ----------------------------------------------------
        session.clear()
        session["usuario_id"]   = usuario["id"]
        session["usuario_rol"]  = usuario["rol"]
        session["usuario_nombre"] = usuario["nombre"]
        session.permanent = recordar  # si "recordar": respeta PERMANENT_SESSION_LIFETIME

        logger.info("Login exitoso — usuario_id=%d  rol=%s", usuario["id"], usuario["rol"])
        flash(f"¡Bienvenido de vuelta, {usuario['nombre']}!", "success")

        # Redirigir a la URL que pedía antes del login (si aplica)
        destino = request.args.get("next") or url_for("index")
        return redirect(destino)

    # GET — mostrar formulario
    return render_template("login.html")


# ------------------------------------------------------------------------------
#  8.2  /logout  — Cerrar sesión
# ------------------------------------------------------------------------------
@app.route("/logout")
def logout():
    """Elimina la sesión activa y redirige al inicio."""
    nombre = session.get("usuario_nombre", "")
    session.clear()

    if nombre:
        flash(f"Hasta pronto, {nombre}. ¡Volvé pronto!", "info")
        logger.info("Logout — usuario: %s", nombre)

    return redirect(url_for("index"))


# ------------------------------------------------------------------------------
#  8.3  /registro  — Crear nueva cuenta
# ------------------------------------------------------------------------------
@app.route("/registro", methods=["GET", "POST"])
def registro():
    """
    GET:  Muestra el formulario de registro.
    POST: Valida los datos, crea el usuario y lo loguea automáticamente.
    """
    global _siguiente_usuario_id

    if "usuario_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        nombre    = request.form.get("nombre", "").strip()
        email     = request.form.get("email", "").strip()
        password  = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        # ---- Validaciones ----------------------------------------------------
        errores = []

        if not nombre or len(nombre) < 2:
            errores.append("El nombre debe tener al menos 2 caracteres.")

        if not _email_valido(email):
            errores.append("El formato del correo no es válido.")

        if len(password) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")

        if password != password2:
            errores.append("Las contraseñas no coinciden.")

        if _buscar_usuario_por_email(email):
            errores.append("Ya existe una cuenta con ese correo electrónico.")

        if errores:
            for error in errores:
                flash(error, "error")
            return redirect(url_for("registro"))

        # ---- Crear usuario ---------------------------------------------------
        nuevo_id = _siguiente_usuario_id
        _siguiente_usuario_id += 1

        _usuarios[nuevo_id] = {
            "id":            nuevo_id,
            "nombre":        nombre,
            "email":         email.lower(),
            "password_hash": _hash_password(password),
            "rol":           "cliente",
            "activo":        True,
            "creado_en":     datetime.now(),
        }

        logger.info("Nuevo usuario registrado — id=%d  email=%s", nuevo_id, email)

        # ---- Auto-login después del registro --------------------------------
        session.clear()
        session["usuario_id"]     = nuevo_id
        session["usuario_rol"]    = "cliente"
        session["usuario_nombre"] = nombre
        session.permanent = True

        flash(f"¡Cuenta creada exitosamente! Bienvenido, {nombre}.", "success")
        return redirect(url_for("index"))

    return render_template("registro.html")


# ==============================================================================
#  9. API REST — Endpoints JSON
#  Prefijo /api/v1/
# ==============================================================================

# ------------------------------------------------------------------------------
#  9.1  POST /api/v1/chatbot/mensaje  — Recibir mensaje del chat
# ------------------------------------------------------------------------------
@app.route("/api/v1/chatbot/mensaje", methods=["POST"])
def api_chatbot_mensaje():
    """
    Recibe un mensaje de texto del usuario desde el frontend del chatbot.

    Body JSON esperado:
        { "mensaje": "¿Cuánto cuesta el pollo entero?" }

    Respuesta JSON:
        {
            "ok": true,
            "respuesta": "...",
            "timestamp": "2024-01-01T12:00:00"
        }

    El historial completo se almacena en la sesión Flask.
    La generación de la respuesta es delegada al modelo de lenguaje
    (Ollama u otro backend externo).
    """
    datos = request.get_json(silent=True)

    if not datos or not isinstance(datos.get("mensaje"), str):
        return jsonify({"ok": False, "error": "El campo 'mensaje' es requerido."}), 400

    mensaje_usuario = datos["mensaje"].strip()

    if not mensaje_usuario:
        return jsonify({"ok": False, "error": "El mensaje no puede estar vacío."}), 400

    if len(mensaje_usuario) > 1000:
        return jsonify({"ok": False, "error": "El mensaje es demasiado largo (máx. 1000 caracteres)."}), 400

    # ---- Guardar mensaje del usuario en historial ---------------------------
    ahora      = datetime.now()
    ts_str     = ahora.isoformat()

    entrada_usuario = {
        "rol":       "usuario",
        "contenido": mensaje_usuario,
        "timestamp": ts_str,
    }

    historial = session.get("chat_historial", [])
    historial.append(entrada_usuario)

    # ---- Construir respuesta (placeholder — conectar con Ollama/LLM) -------
    #  En producción este bloque llama a Ollama o a la API de Claude.
    #  Por ahora devuelve una respuesta de demostración basada en palabras clave.
    from chatbot import responder
respuesta_texto = responder(mensaje_usuario)

# Comentario para forzar actualización
    entrada_asistente = {
            "rol":       "asistente",
            "contenido": respuesta_texto,
            "timestamp": datetime.now().isoformat(),
    }
    historial.append(entrada_asistente)

    # - Limitar historial y guardar en sesión ------------------------------
    max_hist = app.config["CHATBOT_MAX_HISTORY"]
    if len(historial) > max_hist:
        historial = historial[-max_hist:]

    session["chat_historial"] = historial
    session.modified = True  # forzar guardado aunque sea mutable anidado

    logger.debug(
        "Chatbot — mensaje recibido (%d chars)  historial_total=%d",
        len(mensaje_usuario), len(historial),
    )

    return jsonify({
        "ok":        True,
        "respuesta": respuesta_texto,
        "timestamp": entrada_asistente["timestamp"],
    })


# ------------------------------------------------------------------------------
#  9.2  DELETE /api/v1/chatbot/historial  — Borrar historial del chat
# ------------------------------------------------------------------------------
@app.route("/api/v1/chatbot/historial", methods=["DELETE"])
def api_chatbot_borrar_historial():
    """Elimina el historial de chat de la sesión actual."""
    session.pop("chat_historial", None)
    session.pop("chat_iniciado_en", None)
    session.modified = True
    logger.debug("Historial de chat borrado.")
    return jsonify({"ok": True, "mensaje": "Historial eliminado."})


# ------------------------------------------------------------------------------
#  9.3  GET /api/v1/productos  — Listado de productos en JSON
# ------------------------------------------------------------------------------
@app.route("/api/v1/productos")
def api_productos():
    """
    Devuelve el catálogo completo en JSON.
    Acepta los mismos query params que la vista /productos.
    """
    categoria = request.args.get("categoria", "todos").strip().lower()
    busqueda  = request.args.get("q", "").strip().lower()

    resultado = [p for p in _productos if p["disponible"]]

    if categoria != "todos" and categoria in CATEGORIAS:
        resultado = [p for p in resultado if p["categoria"] == categoria]

    if busqueda:
        resultado = [
            p for p in resultado
            if busqueda in p["nombre"].lower() or busqueda in p["descripcion"].lower()
        ]

    return jsonify({
        "ok":       True,
        "total":    len(resultado),
        "productos": resultado,
    })


# ------------------------------------------------------------------------------
#  9.4  GET /api/v1/productos/<int:producto_id>  — Detalle de producto
# ------------------------------------------------------------------------------
@app.route("/api/v1/productos/<int:producto_id>")
def api_producto_detalle(producto_id: int):
    """Devuelve el detalle de un producto específico por ID."""
    producto = next((p for p in _productos if p["id"] == producto_id), None)
    if producto is None:
        return jsonify({"ok": False, "error": "Producto no encontrado."}), 404
    return jsonify({"ok": True, "producto": producto})


# ------------------------------------------------------------------------------
#  9.5  POST /api/v1/pedidos  — Crear un pedido
# ------------------------------------------------------------------------------
@app.route("/api/v1/pedidos", methods=["POST"])
def api_crear_pedido():
    """
    Registra un nuevo pedido.

    Body JSON esperado:
        {
            "nombre":   "María García",
            "telefono": "+591 76543210",
            "zona":     "Miraflores",
            "items": [
                { "producto_id": 1, "cantidad": 2 },
                { "producto_id": 3, "cantidad": 1 }
            ],
            "notas": "Sin sal adicional"   (opcional)
        }
    """
    global _siguiente_pedido_id

    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"ok": False, "error": "Se esperaba JSON en el body."}), 400

    # ---- Validaciones -------------------------------------------------------
    errores = []

    nombre   = (datos.get("nombre") or "").strip()
    telefono = (datos.get("telefono") or "").strip()
    zona     = (datos.get("zona") or "").strip()
    items    = datos.get("items", [])
    notas    = (datos.get("notas") or "").strip()

    if not nombre:
        errores.append("El campo 'nombre' es obligatorio.")
    if not telefono:
        errores.append("El campo 'telefono' es obligatorio.")
    if not zona:
        errores.append("El campo 'zona' es obligatorio.")
    if not isinstance(items, list) or len(items) == 0:
        errores.append("El pedido debe incluir al menos un ítem.")

    if errores:
        return jsonify({"ok": False, "errores": errores}), 422

    # ---- Resolver productos e ítems -----------------------------------------
    items_resueltos = []
    total           = 0.0

    for item in items:
        pid      = item.get("producto_id")
        cantidad = item.get("cantidad", 1)

        if not isinstance(pid, int) or not isinstance(cantidad, int) or cantidad < 1:
            errores.append(f"Ítem inválido: {item}")
            continue

        producto = next((p for p in _productos if p["id"] == pid), None)
        if producto is None:
            errores.append(f"Producto con id={pid} no existe.")
            continue

        if not producto["disponible"]:
            errores.append(f"El producto '{producto['nombre']}' no está disponible.")
            continue

        subtotal = round(producto["precio"] * cantidad, 2)
        total   += subtotal

        items_resueltos.append({
            "producto_id":     pid,
            "nombre_producto": producto["nombre"],
            "precio_unitario": producto["precio"],
            "cantidad":        cantidad,
            "subtotal":        subtotal,
        })

    if errores:
        return jsonify({"ok": False, "errores": errores}), 422

    # ---- Crear el pedido ----------------------------------------------------
    pedido_id  = _siguiente_pedido_id
    _siguiente_pedido_id += 1

    nuevo_pedido = {
        "id":          pedido_id,
        "nombre":      nombre,
        "telefono":    telefono,
        "zona":        zona,
        "notas":       notas,
        "items":       items_resueltos,
        "total_bs":    round(total, 2),
        "estado":      "pendiente",       # pendiente | confirmado | entregado | cancelado
        "creado_en":   datetime.now().isoformat(),
        "usuario_id":  session.get("usuario_id"),  # None si es anónimo
    }

    _pedidos.append(nuevo_pedido)

    logger.info(
        "Nuevo pedido #%d — cliente: %s  total: Bs. %.2f  ítems: %d",
        pedido_id, nombre, total, len(items_resueltos),
    )

    return jsonify({
        "ok":       True,
        "pedido_id": pedido_id,
        "total_bs":  nuevo_pedido["total_bs"],
        "estado":    "pendiente",
        "mensaje":   "¡Pedido recibido! Te contactaremos en menos de 2 horas.",
    }), 201


# ------------------------------------------------------------------------------
#  9.6  POST /api/v1/newsletter  — Suscripción al newsletter
# ------------------------------------------------------------------------------
@app.route("/api/v1/newsletter", methods=["POST"])
def api_newsletter():
    """
    Registra un correo para el newsletter y envía correo de bienvenida.
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"ok": False, "error": "Se esperaba JSON."}), 400

    email = (datos.get("email") or "").strip().lower()

    if not _email_valido(email):
        return jsonify({"ok": False, "error": "Correo electrónico no válido."}), 422

    # --- AQUÍ ESTÁ EL CAMBIO ---
    # Llamamos a la función de Brevo que configuramos en el Paso 1
    enviar_correo_pedido(email, "Nuevo Miembro de Avicor") 
    # ---------------------------

    logger.info("Nueva suscripción al newsletter y correo enviado: %s", email)

    return jsonify({
        "ok":      True,
        "mensaje": "¡Gracias! Ya sos parte de la familia Avicor. Revisa tu correo.",
    })


# ------------------------------------------------------------------------------
#  9.7  GET /api/v1/sesion  — Estado de la sesión actual
# ------------------------------------------------------------------------------
@app.route("/api/v1/sesion")
def api_sesion():
    """Devuelve información básica de la sesión (útil para el frontend SPA)."""
    usuario = g.get("usuario_actual")
    return jsonify({
        "autenticado": usuario is not None,
        "usuario": {
            "id":     usuario["id"]     if usuario else None,
            "nombre": usuario["nombre"] if usuario else None,
            "rol":    usuario["rol"]    if usuario else None,
        },
        "chat_mensajes": len(session.get("chat_historial", [])),
    })


# ==============================================================================
#  10. MANEJADORES DE ERROR
# ==============================================================================

@app.errorhandler(400)
def error_400(e):
    logger.warning("400 Bad Request: %s", request.url)
    return render_template("errores/400.html", error=str(e)), 400


@app.errorhandler(403)
def error_403(e):
    logger.warning("403 Forbidden: %s — usuario=%s", request.url, session.get("usuario_id"))
    return render_template("errores/403.html", error=str(e)), 403


@app.errorhandler(404)
def error_404(e):
    logger.info("404 Not Found: %s", request.url)
    return render_template("errores/404.html", error=str(e)), 404


@app.errorhandler(405)
def error_405(e):
    return render_template("errores/405.html", error=str(e)), 405


@app.errorhandler(500)
def error_500(e):
    logger.error("500 Internal Server Error: %s — %s", request.url, str(e))
    return render_template("errores/500.html", error=str(e)), 500

# --- Función para enviar correos con Brevo ---
def enviar_correo_pedido(email_cliente, nombre_cliente):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    
    configuration = sib_api_v3_sdk.Configuration()
    # Pega aquí la clave larga que copiaste de Brevo
    configuration.api_key['api-key'] = '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'
    
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    
    contenido_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email_cliente}],
        sender={"name": "Origen Avicor", "email": "tu_correo@gmail.com"},
        subject="¡Gracias por tu pedido en Origen Avicor!",
        html_content=f"""
            <div style='font-family: Arial, sans-serif; color: #333;'>
                <h1 style='color: #4CAF50;'>¡Hola {nombre_cliente}!</h1>
                <p>Hemos recibido tu interés por nuestros productos de Coroico.</p>
                <p>Nuestros precios actuales:</p>
                <ul>
                    <li><b>Pack Familiar:</b> Bs. 145</li>
                    <li><b>Pollo Entero:</b> Bs. 65</li>
                </ul>
                <p>En breve un asesor te contactará al teléfono que registraste. ¡Gracias por elegir lo natural!</p>
            </div>
        """
    )
    try:
        api_instance.send_transac_email(contenido_email)
        logger.info("Correo de confirmación enviado a: %s", email_cliente)
        return True
    except ApiException as e:
        logger.error("Error al enviar correo con Brevo: %s", e)
        return False
# ==============================================================================
#  11. FUNCIONES AUXILIARES PRIVADAS
# ==============================================================================

def _parsear_int(valor, default: int = 0) -> int:
    """Convierte un valor a int de forma segura; devuelve `default` si falla."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def _email_valido(email: str) -> bool:
    """Valida el formato básico de un correo electrónico con regex."""
    patron = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(patron, email))


def _respuesta_demo_chatbot(mensaje: str) -> str:
    """
    Genera una respuesta de demostración basada en palabras clave.

    NOTA: Esta función es un placeholder.
    En producción, reemplazar por una llamada a:
        - Ollama local (llama3, mistral, etc.)
        - API de Anthropic Claude
        - Cualquier otro LLM

    Ejemplo de integración con Ollama:
        import requests
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3", "prompt": mensaje, "stream": False}
        )
        return r.json()["response"]
    """
    msg = mensaje.lower()

    if any(w in msg for w in ["precio", "costo", "cuánto", "cuanto", "vale", "bs"]):
        return (
            "¡Con gusto! Nuestros precios actuales:\n"
            "• Pollo entero: Bs. 65\n"
            "• Pechuga fileteada 500g: Bs. 48\n"
            "• Pollo orgánico: Bs. 80\n"
            "• Pack Familiar: Bs. 145 (ahorrás 15%)\n"
            "• Pack Parrillero: Bs. 115\n\n"
            "¿Te interesa alguno en particular?"
        )

    if any(w in msg for w in ["entreg", "envío", "envio", "despacho", "llegar"]):
        return (
            "Realizamos entregas a domicilio en La Paz de lunes a sábado, "
            "de 7:00 am a 6:00 pm, y los domingos de 8:00 am a 2:00 pm.\n\n"
            "El envío es GRATIS en pedidos mayores a Bs. 120. "
            "Para zonas alejadas puede aplicar un cargo adicional. "
            "¿En qué zona estás?"
        )

    if any(w in msg for w in ["coroico", "yungas", "origen", "granja", "produce"]):
        return (
            "Nuestras aves son criadas en Coroico, en los Yungas de La Paz, "
            "a 1.700 msnm. Trabajamos con 12 familias productoras locales "
            "que crían los pollos en libertad, sin hormonas y con alimentación "
            "100% natural. ¡El campo boliviano en cada plato!"
        )

    if any(w in msg for w in ["hormona", "antibi", "quím", "natural", "orgán"]):
        return (
            "¡Nunca usamos hormonas de crecimiento ni antibióticos preventivos! "
            "Nuestras aves se alimentan de maíz criollo, quinua y hierbas del campo. "
            "El pollo orgánico certificado además lleva sello de trazabilidad QR "
            "para que puedas verificar todo el proceso."
        )

    if any(w in msg for w in ["pedir", "comprar", "orden", "pedido", "cómo compro"]):
        return (
            "Podés hacer tu pedido de tres formas:\n"
            "1️⃣ Directamente desde nuestra página en /productos\n"
            "2️⃣ Por WhatsApp al +591 79 000 000\n"
            "3️⃣ Enviándonos un mensaje aquí y un asesor te contacta\n\n"
            "¿Qué producto te interesa?"
        )

    if any(w in msg for w in ["hola", "buenas", "buenos", "hey", "hi", "buen día"]):
        return (
            "¡Hola! 🐔 Bienvenido al chatbot de Origen Avicor. "
            "Soy tu asistente virtual y puedo ayudarte con:\n"
            "• Información de productos y precios\n"
            "• Zonas y horarios de entrega\n"
            "• Hacer un pedido\n"
            "• Conocer nuestro origen en Coroico\n\n"
            "¿En qué puedo ayudarte hoy?"
        )

    if any(w in msg for w in ["gracias", "thank", "perfecto", "genial", "excelente"]):
        return (
            "¡Con mucho gusto! 😊 Es un placer ayudarte. "
            "¿Hay algo más en lo que pueda colaborar?"
        )

    # Respuesta por defecto
    return (
        "Entendí tu consulta. Puedo ayudarte con información sobre nuestros "
        "productos, precios, entregas y el origen de nuestro pollo en Coroico. "
        "También podés escribirnos al WhatsApp +591 79 000 000 para una "
        "atención más personalizada. ¿Qué necesitás saber?"
    )


# ==============================================================================
#  12. PUNTO DE ENTRADA
# ==============================================================================

