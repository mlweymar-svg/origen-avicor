# chatbot.py – Asistente Virtual Avi · Origen Avicor
# Estructura original conservada íntegramente.
# Mejoras añadidas:
#   - Integración con Ollama (modelo mistral) como motor principal
#   - Fallback al motor de reglas local si Ollama no está disponible
#   - Prompt de sistema con identidad completa de Origen Avicor
#   - Ruta Flask /chat para recibir mensajes del frontend
#   - Manejo robusto de errores y timeouts
#   - Función responder() conservada para uso offline / consola

import random
import unicodedata
import json
import logging
import os
import re
import time

import requests
from flask import Flask, request, jsonify, render_template, session
# Tus importaciones actuales...
from app import app 

# ... sigue tu código igual ...
# ─────────────────────────────────────────
#  Configuración
# ─────────────────────────────────────────

OLLAMA_BASE_URL  = "http://127.0.0.1:11434"
OLLAMA_MODEL     = "phi3"
OLLAMA_TIMEOUT   = 120  # Con phi3, 60 segundos son más que suficientes
MAX_HIST_CONTEXT = 16

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("FLASK_DEBUG", "1") == "1" else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  chatbot — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("avicor.chatbot")

# ─────────────────────────────────────────
#  Prompt de sistema — identidad Avicor
# ─────────────────────────────────────────

SYSTEM_PROMPT = """
Eres Avi, el asistente virtual inteligente de Origen Avicor. No actúes de manera fría o robótica; eres el embajador de un producto premium, artesanal y consciente. Tu misión es asesorar al cliente usando técnicas de marketing sensorial: evoca de forma apetitosa texturas tiernas, la jugosidad, la frescura inigualable del campo y el entorno natural de los Yungas, La Paz para despertar el deseo de compra.

TONO Y ESTILO:
- Amable, servicial, cercano y cálido. Hablas en español boliviano utilizando "vos".
- Respuestas estrictamente concisas (máximo 5 líneas) para optimizar la velocidad de procesamiento en entornos locales.
- Uso sutil y estratégico de emojis (🐔 🌿 ✨ 📦 🚚).

REGLAS DE INTERACCIÓN (ESTRATEGIA CORPORATIVA):

1. ORIGEN Y TRAZABILIDAD (CONFIANZA):
Cuando pregunten por la crianza o si el producto es natural, destaca con orgullo el origen en Coroico, Yungas (1.700 msnm, agua de vertiente). Explica de forma provocativa que nuestras aves crecen libres bajo el sol, sin jaulas, alimentadas con maíz criollo, quinua y hierbas silvestres (cero hormonas, cero antibióticos). Menciona que garantizamos total transparencia mediante un código QR en cada empaque biodegradable al vacío para ver la granja de origen (red de 12 familias productoras).

2. PEDIDOS SENCILLOS:
Si el cliente manifiesta intención de compra, guíalo de forma directa y simplificada paso a paso sin saturarlo de texto. Solicita de manera ordenada: Nombre, producto/corte deseado, teléfono de contacto y zona de entrega en La Paz.

3. COTIZADOR Y CATÁLOGO DE PRODUCTOS COMPLETO (VALORES EXACTOS EN Bs.):
Usa única y estrictamente este catálogo oficial. Está prohibido inventar precios:
• Pollo Entero Avicor (tierno, fresco y jugoso) → Bs. 65 / unidad (~2.2 kg) [más vendido]
• Pollo Orgánico Certificado (premium, libre pastoreo) → Bs. 80 / unidad (~2.5 kg) [premium, QR trazable]
• Pollo Entero Pequeño → Bs. 52 / unidad (~1.5 kg)
• Pechuga fileteada (fresca y limpia, magra y sin grasa) → Bs. 48 / 500 g (sin hueso, sin piel)
• Pechuga entera con hueso → Bs. 55 / 1 kg
• Muslos sazonados (marinado natural, listos para dorar) → Bs. 38 / pack x4
• Piernas con hueso (jugosas y frescas) → Bs. 32 / 500 g
• Menudencias mix → Bs. 18 / 300 g
• Hígado de pollo fresco → Bs. 15 / 250 g
• Pack Familiar Completo (pollo entero + pechugas + muslos) → Bs. 145 / pack (-15% de ahorro)
• Pack Parrillero (muslos + piernas + alitas marinadas listas para el fuego) → Bs. 115 / pack
• Pack Semanal Económico → Bs. 95 / pack (-12% de ahorro)
* NOTA DE MARKETING: El envío es completamente GRATIS en pedidos iguales o mayores a Bs. 120.

4. COBERTURA Y DELIVERY:
Las entregas se realizan en La Paz de lunes a sábado (7:00 a 18:00 hs) y domingos (8:00 a 14:00 hs). Asegura al cliente que el traslado se realiza bajo una estricta cadena de frío ininterrumpida para preservar intactas las propiedades y la frescura viva del pollo de campo.

5. CONEXIÓN AUDIOVISUAL Y REDES:
Dado que el material audiovisual de los Yungas está en fase de preparación, ante consultas sobre videos del proceso o recetas, responde con entusiasmo: "¡Muy pronto tendremos listos videos deliciosos de nuestras recetas y del hermoso proceso de crianza en Coroico para nuestras redes en TikTok y Facebook! Estate atento."

6. CAPTACIÓN DE CLIENTES AL INICIO:
Al procesar el primer saludo del usuario o la apertura de la sesión, añade siempre una invitación sutil al inicio de tu respuesta: "¡Hola! Antes de empezar, ¿te gustaría dejarme tu número de WhatsApp? Así podré enviarte de forma prioritaria nuestros combos dorados, recetas de campo y ofertas exclusivas de la semana."

7. DESVÍO EFICIENTE A ATENCIÓN HUMANA:
Ante consultas que impliquen reclamos, quejas o datos técnicos fuera de este contexto, deriva amablemente al cliente diciendo: "Para darte una atención perfecta y detallada, te contactaré de inmediato con mis compañeros humanos", proporcionando el enlace de soporte WhatsApp: +591 79 000 000.

REGLA CRÍTICA: Nunca inventes datos ni compares negativamente a Origen Avicor con la competencia industrial tradicional.
""".strip()
CATALOGO_OFICIAL = """
PRECIOS OFICIALES:
- Pollo Entero Avicor: Bs. 65 (~2.2 kg)
- Pollo Orgánico: Bs. 80 (~2.5 kg)
- Pollo Entero Pequeño: Bs. 52
- Pechuga fileteada: Bs. 48 / 500 g
- Pechuga c/hueso: Bs. 55 / 1 kg
- Muslos sazonados: Bs. 38 / pack x4
- Piernas: Bs. 32 / 500 g
- Menudencias: Bs. 18 / 300 g
- Hígado: Bs. 15 / 250 g
- Pack Familiar: Bs. 145
- Pack Parrillero: Bs. 115
- Pack Semanal: Bs. 95
(Envío GRATIS en pedidos >= Bs. 120)
""".strip()
# ─────────────────────────────────────────
#  Utilidad: normalizar texto
# ─────────────────────────────────────────

def normalizar(texto: str) -> str:
    """Minúsculas + elimina tildes para comparación flexible."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# ─────────────────────────────────────────
#  Base de conocimiento (motor de reglas original conservado)
# ─────────────────────────────────────────

REGLAS = [

    # ── SALUDO ──
    {
        "claves": [
            "hola", "buenas", "buenos", "saludos", "hey", "hi",
            "que tal", "como estas", "ola", "buen dia", "buen tarde"
        ],
        "respuestas": [
            "¡Hola! 👋 Soy Avi, el asistente de Origen Avicor. "
            "Puedo ayudarte con precios, pedidos, beneficios y nuestro origen en Coroico. "
            "¿En qué te puedo ayudar?",

            "¡Buenas! 🐔 Soy Avi de Origen Avicor. Preguntame sobre productos, precios, "
            "entrega o cómo hacer tu pedido. ¡Estoy aquí!",

            "¡Hola! Me alegra que estés aquí. Soy tu asistente virtual de Origen Avicor. "
            "¿En qué te puedo ayudar hoy?",
        ]
    },

    # ── PRECIOS ──
    {
        "claves": [
            "precio", "cuanto", "costo", "vale", "valor",
            "bs", "bolivianos", "cuanto cuesta", "cuanto vale"
        ],
        "respuestas": [
            "💰 Nuestros precios actuales:\n"
            "• Pollo entero: Bs. 65 (~2.2 kg)\n"
            "• Pollo orgánico: Bs. 80 (~2.5 kg, QR trazable)\n"
            "• Pechuga fileteada: Bs. 48 / 500 g\n"
            "• Pack Familiar: Bs. 145 (ahorrás 15%)\n"
            "• Pack Parrillero: Bs. 115\n"
            "Envío gratis en pedidos mayores a Bs. 120. ¿Te interesa alguno?",

            "🐔 Precios Origen Avicor:\n"
            "• Pollo Entero → Bs. 65\n"
            "• Pollo Orgánico → Bs. 80\n"
            "• Pechugas → Bs. 48 / 500 g\n"
            "• Pack Familiar → Bs. 145 (-15%)\n"
            "Todos frescos, sin hormonas, directo de Coroico.",
        ]
    },

    # ── PEDIDO ──
    {
        "claves": ["pedido", "pedir", "comprar", "quiero", "ordenar", "llevar", "encargar"],
        "respuestas": [
            "🛒 ¡Con gusto! Para hacer tu pedido:\n"
            "📞 WhatsApp: +591 79 000 000\n"
            "🕗 Lun-Sáb 7:00-18:00, Dom 8:00-14:00\n"
            "📦 Envío gratis en pedidos mayores a Bs. 120\n"
            "¿Qué producto y cantidad necesitás?",

            "¡Vamos! 🐔 Decime qué necesitás:\n"
            "• Pollo Entero (Bs. 65)\n"
            "• Pechuga fileteada (Bs. 48 / 500 g)\n"
            "• Pack Familiar (Bs. 145)\n"
            "O escribinos al WhatsApp +591 79 000 000.",
        ]
    },

    # ── BENEFICIOS / NATURAL / ORGÁNICO ──
    {
        "claves": [
            "natural", "quimico", "hormona", "alimentacion",
            "crianza", "campo", "libre", "como crian",
            "organico", "organica", "sin antibiotico", "certificado",
            "beneficio", "diferencia", "por que"
        ],
        "respuestas": [
            "🌿 Crianza 100% natural en Coroico:\n"
            "• Campo abierto, sin jaulas ni hacinamiento\n"
            "• Alimentación: maíz criollo, quinua y hierbas silvestres\n"
            "• Cero hormonas y cero antibióticos preventivos\n"
            "• Trazabilidad QR en cada empaque\n"
            "• Empaque biodegradable al vacío\n"
            "¡El sabor del campo boliviano en tu mesa!",

            "✅ ¿Por qué elegirnos?\n"
            "• Productores directos de Coroico (sin intermediarios)\n"
            "• Sin hormonas ni antibióticos — garantizado\n"
            "• Peso real, precio justo y frescura total\n"
            "• Más de 300 familias bolivianas confían en nosotros (4.9 estrellas)\n"
            "¿Querés hacer un pedido?",
        ]
    },

    # ── ORIGEN COROICO ──
    {
        "claves": [
            "coroico", "yungas", "origen", "donde", "ubicacion",
            "granja", "produce", "lugar", "estan"
        ],
        "respuestas": [
            "📍 Nuestras granjas están en Coroico, Yungas de La Paz, "
            "a 1.700 msnm. Clima subtropical ideal (18-24°C), agua de vertiente "
            "y campo abierto. Trabajamos con 12 familias productoras locales.",

            "Coroico, en los Yungas bolivianos 🌿. Producción propia, entrega directa "
            "a La Paz. Sin intermediarios. Eso garantiza frescura y precio justo.",
        ]
    },

    # ── ENTREGA / ENVÍO ──
    {
        "claves": [
            "entrega", "delivery", "envio", "llegar", "zona",
            "lleva", "domicilio", "reparto", "despacho",
            "cuantos dias", "cuando llega", "tiempo entrega", "demora"
        ],
        "respuestas": [
            "🚚 Entregamos en La Paz y alrededores:\n"
            "• Lun-Sáb: 7:00 am a 6:00 pm\n"
            "• Dom: 8:00 am a 2:00 pm\n"
            "• Envío GRATIS en pedidos mayores o iguales a Bs. 120\n"
            "Al hacer tu pedido te confirmamos el tiempo según tu zona.",

            "Entregamos en La Paz con cadena de frío ininterrumpida. 🌿 "
            "Gratis si tu pedido supera Bs. 120. ¿En qué zona estás?",
        ]
    },

    # ── CONTACTO / HORARIO ──
    {
        "claves": [
            "contacto", "telefono", "whatsapp", "llamar", "numero",
            "comunicar", "escribir", "horario", "hora", "atienden"
        ],
        "respuestas": [
            "📞 Contacto Origen Avicor:\n"
            "• WhatsApp/Tel: +591 79 000 000\n"
            "• Email: hola@origenavicor.bo\n"
            "• Horario: Lun-Sáb 7:00-18:00, Dom 8:00-14:00\n"
            "• Ubicación: Sopocachi, La Paz (granjas en Coroico)",

            "¡Escribinos! 📱 +591 79 000 000 por WhatsApp o llamada. "
            "Lun-Sáb de 7 a 18 hs. ¡Respuesta rápida garantizada!",
        ]
    },

    # ── PACK / COMBO ──
    {
        "claves": ["pack", "combo", "familiar", "parrillero", "semanal", "ahorro"],
        "respuestas": [
            "🎁 Nuestros packs con descuento:\n"
            "• Pack Familiar → Bs. 145 (antes Bs. 170, -15%)\n"
            "  Incluye: pollo entero + 1 kg pechugas + 1/2 kg muslos\n"
            "• Pack Parrillero → Bs. 115 (para 4-6 personas)\n"
            "• Pack Semanal Económico → Bs. 95 (-12%)\n"
            "¿Cuál se adapta mejor a vos?",
        ]
    },

    # ── RECOMENDACIÓN ──
    {
        "claves": [
            "recomienda", "cual es mejor", "cual compro",
            "para familia", "para evento", "para dieta", "para restaurante"
        ],
        "respuestas": [
            "💡 Te asesoro según tu necesidad:\n"
            "• Familia (4-6 personas) → Pack Familiar (Bs. 145)\n"
            "• Evento o reunión → Pack Parrillero (Bs. 115)\n"
            "• Dieta o salud → Pollo Orgánico Certificado (Bs. 80)\n"
            "• Presupuesto ajustado → Pack Semanal (Bs. 95)\n"
            "¿Cuál se adapta mejor a vos?",
        ]
    },

    # ── DESCUENTO / OFERTA ──
    {
        "claves": [
            "descuento", "oferta", "promocion", "barato",
            "precio especial", "rebaja", "convenio"
        ],
        "respuestas": [
            "🎁 Los packs ya incluyen descuentos de hasta 15%. "
            "Para pedidos corporativos, escribinos al WhatsApp +591 79 000 000.",

            "💰 Si querés aprovechar al máximo, optá por nuestros packs. "
            "¿Te paso los precios?",
        ]
    },

    # ── RECETAS ──
    {
        "claves": [
            "receta", "preparar", "cocinar", "cocina",
            "como hacer", "sopa", "asado", "frito", "guiso"
        ],
        "respuestas": [
            "👨‍🍳 ¡Con pollo de campo el resultado siempre es mejor!\n"
            "• Asado o parrilla → Pollo Entero (Bs. 65)\n"
            "• Sopa o guiso → Piernas con hueso (Bs. 32)\n"
            "• Dieta fitness → Pechuga fileteada\n"
            "¿Te ayudo a elegir el corte ideal?",
        ]
    },

    # ── GRACIAS ──
    {
        "claves": [
            "gracias", "muchas gracias", "genial", "perfecto",
            "excelente", "buenisimo", "ok", "listo", "entendido"
        ],
        "respuestas": [
            "¡De nada! 😊 Estoy aquí si necesitás más info o querés hacer tu pedido.",
            "¡Con gusto! 🐔 ¿Hay algo más en lo que pueda ayudarte?",
            "¡Fue un placer! 🌿 Cualquier duda, aquí estoy.",
        ]
    },

    # ── DESPEDIDA ──
    {
        "claves": ["adios", "chau", "bye", "hasta luego", "nos vemos", "ciao"],
        "respuestas": [
            "¡Hasta pronto! 👋 Fue un placer asesorarte. "
            "Recordá que estamos en +591 79 000 000.",
            "¡Nos vemos! 🐔 Cualquier pedido o duda, aquí estaremos. ¡Que disfrutes tu día!",
        ]
    },
]

RESPUESTAS_DEFAULT = [
    "Mmm, no tengo esa información exacta. 🤔 Puedo ayudarte con precios, "
    "pedidos, beneficios del producto u origen en Coroico. ¿Qué necesitás?",

    "No encontré datos sobre eso, pero podés escribirnos al "
    "WhatsApp +591 79 000 000 para una atención personalizada. 🐔",

    "¡Esa consulta se escapa un poco! 😅 Preguntame sobre precios, "
    "entregas, crianza natural o cómo hacer tu pedido. ¡Estoy para asesorarte!",
]


# ─────────────────────────────────────────
#  Motor de reglas local (original conservado)
# ─────────────────────────────────────────

def responder_local(mensaje: str) -> str:
    msj = mensaje.lower()
    
    if "precio" in msj or "cuanto" in msj or "costo" in msj:
        return "Nuestros precios: Pollo Entero Bs. 65, Pollo Orgánico Bs. 80, Packs desde Bs. 95. ¡Calidad directa de Coroico!"
    if "pack" in msj:
        return "¡Ahorrá con nuestros packs! Pack Familiar (Bs. 145), Pack Parrillero (Bs. 115) o Pack Semanal (Bs. 95)."
    if "origen" in msj or "donde" in msj or "coroico" in msj:
        return "Nuestros pollos crecen libres en Coroico, Yungas (1.700 msnm), alimentados con maíz, quinua y hierbas. ¡Cero hormonas!"
    if "pedido" in msj or "hacer" in msj or "comprar" in msj:
        return "¡Claro! Para tu pedido necesito: Nombre, producto/corte deseado, teléfono y zona de entrega. Escribinos a nuestro WhatsApp: +591 79 000 000."
    if "entrega" in msj or "delivery" in msj or "zona" in msj:
        return "Entregamos en La Paz, Lun-Sáb 7:00-18:00 y Dom 8:00-14:00. ¡Envío GRATIS en pedidos mayores a Bs. 120!"
    if "natural" in msj or "crianza" in msj:
        return "Criamos aves libres, sin jaulas ni antibióticos, con agua de vertiente. Garantizamos transparencia total con código QR en cada empaque."
    
    return "¡Hola! Soy Avi. Estoy procesando tu consulta. Para ver detalles completos, te recomiendo visitar nuestra sección de Productos."

def obtener_respuesta(mensaje: str) -> str:
    """Interfaz pública corregida."""
    return _obtener_respuesta(mensaje, historial=[])

# ─────────────────────────────────────────
#  Integración Ollama / Mistral
# ─────────────────────────────────────────

def _ollama_disponible() -> bool:
    """Verifica que Ollama esté activo y el modelo llama2 esté instalado."""
    try:
        # Usamos la IP directa que es más rápida y segura
        resp = requests.get(
            "http://127.0.0.1:11434/api/tags",
            timeout=3,
        )
        resp.raise_for_status()
        modelos = [m.get("name", "") for m in resp.json().get("models", [])]
        
        # BUSCAMOS SOLAMENTE QUE EXISTA LA PALABRA "llama2" (más seguro y flexible)
        disponible = any("llama2" in m.lower() for m in modelos)
        
        if not disponible:
            logger.warning(
                "Modelo Llama2 no encontrado en tu Ollama. Tienes: %s", modelos,
            )
        return disponible
    except Exception as exc:
        logger.warning("Ollama no disponible en el puerto local: %s", exc)
        return True  # Mantenemos el True que pusimos antes para forzar el paso

def _llamar_ollama(mensaje: str, historial: list) -> str:
    """Llama a la API de Ollama con la identidad de Avicor y el catálogo inyectado."""
    
    # 1. Mensaje de sistema principal (Tu identidad completa)
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 2. INYECCIÓN INTELIGENTE DEL CATÁLOGO
    # Solo se inyecta si el usuario pregunta por cosas comerciales, 
    # manteniendo el prompt ligero el resto del tiempo.
    if any(k in mensaje.lower() for k in ["precio", "costo", "cuanto", "producto", "pack", "valor", "oferta", "cuanto vale"]):
        mensajes.append({
            "role": "system", 
            "content": f"REGLA DE ORO: Para precios y productos, usa exclusivamente estos datos: {CONOCIMIENTO_WEB}"
        })
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
def _parsear_int(valor, default=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default
        
    # 3. Contexto de historial
    for entrada in historial[-MAX_HIST_CONTEXT:]:
        rol = "user" if entrada.get("rol") == "usuario" else "assistant"
        contenido = entrada.get("contenido", "").strip()
        if contenido:
            mensajes.append({"role": rol, "content": contenido})

    # 4. Mensaje del usuario
    mensajes.append({"role": "user", "content": mensaje})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": mensajes,
        "stream": False,
        "options": {
            "temperature": 0.5, # Bajamos un poco la temperatura para que sea más preciso
            "num_predict": 200,
        },
    }

    inicio = time.monotonic()

    try:
        http = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=None, 
        )
        http.raise_for_status()
        datos = http.json()

        contenido = datos.get("message", {}).get("content", "").strip()

        if not contenido:
            raise ValueError("Respuesta vacía de Ollama.")

        logger.debug("Ollama respondió en %.2fs", time.monotonic() - inicio)
        return _limpiar_respuesta(contenido)

    except Exception as exc:
        logger.error(f"Error crítico en Ollama: {exc}")
        raise exc

def _limpiar_respuesta(texto: str) -> str:
    """Elimina prefijos innecesarios que algunos modelos añaden y normaliza saltos."""
    texto = re.sub(r"^(Avi|Asistente|Assistant)\s*:\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    lineas = [l.rstrip() for l in texto.split("\n")]
    return "\n".join(lineas).strip()


def _sanitizar(texto: str) -> str:
    """Elimina caracteres de control y colapsa espacios múltiples."""
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return texto.strip()


# ─────────────────────────────────────────
#  Función principal — elige motor
# ─────────────────────────────────────────
def _obtener_respuesta(mensaje: str, historial: list) -> str:
    """Función optimizada: Responde botones al instante, IA para lo demás."""
    mensaje_sanitizado = _sanitizar(mensaje)
    if not mensaje_sanitizado:
        return "Por favor escribí tu consulta y te ayudo. 🐔"

    # 1. ENRUTAMIENTO DE ALTA VELOCIDAD (Botones)
    # Si la consulta contiene palabras clave de los botones, respondemos localmente al instante
    claves_rapidas = ["precio", "costo", "cuanto", "pedido", "natural", "origen", "entrega", "pack", "horario"]
    if any(k in mensaje_sanitizado.lower() for k in claves_rapidas):
        return responder_local(mensaje_sanitizado)

    # 2. IA PARA CONSULTAS ABIERTAS
    # Si no es un botón, le damos el paso a Ollama
    try:
        if _ollama_disponible():
            respuesta_ia = _llamar_ollama(mensaje_sanitizado, historial)
            if respuesta_ia and respuesta_ia.strip():
                return respuesta_ia
    except Exception as exc:
        logger.warning(f"La IA falló, usando respaldo local. Error: {exc}")

    # 3. RESPALDO FINAL
    return responder_local(mensaje_sanitizado)

# ─────────────────────────────────────────
#  Flask — rutas del chatbot
# ─────────────────────────────────────────

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "avicor-chatbot-dev-key")

MAX_HISTORIAL = 50  # mensajes máximos en sesión
# BASE DE DATOS REAL DE ORIGEN AVICOR (Copiar exactamente esto)
CONOCIMIENTO_WEB = """
ESTA ES LA ÚNICA INFORMACIÓN VÁLIDA PARA RESPONDER:

1. PRODUCTOS Y PRECIOS:
- Pollo Entero Avicor: Bs. 65 por unidad (~2.2 kg). Criado en campo abierto.
- Pollo Orgánico Certificado: Bs. 80 por unidad (~2.5 kg). Incluye QR de trazabilidad.
- Pechugas: Bs. 48 (empaque al vacío de 500g o 1kg).
- Pack Familiar Completo: Bs. 145 (Incluye 1 pollo entero + 1kg pechugas + 1/2kg muslos). ¡Es el que más ahorra (15%)!

2. HISTORIA Y VALORES (Pestaña Nosotros):
- Ubicación: Granja en Coroico, Yungas de La Paz.
- Trayectoria: Empezamos en 2015 con 200 aves. En 2021 creamos una red de 12 familias productoras.
- Calidad: Crecimiento natural, sin hormonas ni antibióticos, sabor de verdad.

3. LOGÍSTICA:
- Entregas: La Paz y El Alto.
- Acción: Si el cliente quiere comprar, instrúyele que haga clic en el botón naranja de "Comprar" o vaya a la pestaña de "Productos".
"""
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
    
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chatbot")
def chatbot_page():
    if "historial" not in session:
        session["historial"] = []
    return render_template("chatbot.html", historial=session["historial"])

@app.route("/api/chat", methods=["POST"])
def chat():
    datos = request.get_json(silent=True) or {}
    mensaje = str(datos.get("mensaje") or datos.get("message") or "").strip()

    if not mensaje:
        return jsonify({"ok": False, "error": "El mensaje no puede estar vacío."}), 400

    # 1. CAPA DE IDENTIFICACIÓN (Flujo de 2 pasos)
    if "usuario_nombre" not in session:
        # Paso 1: Guardar el nombre
        session["usuario_nombre"] = mensaje
        respuesta = f"¡Mucho gusto, {mensaje}! Soy Avi, tu asistente de Origen Avicor. Para enviarte ofertas exclusivas, ¿me podrías dejar tu número de WhatsApp?"
        return jsonify({"ok": True, "response": respuesta, "motor": "identificacion"})

    if "usuario_telefono" not in session:
        # Paso 2: Guardar el teléfono y registrar el lead
        session["usuario_telefono"] = mensaje
        # Aquí guardamos los datos en tu archivo de texto
        guardar_lead(session["usuario_nombre"], session["usuario_telefono"])
        
        respuesta = "¡Excelente! Ya estás registrado. Ahora, ¿en qué puedo ayudarte a saborear hoy? 🌿"
        return jsonify({"ok": True, "response": respuesta, "motor": "identificacion"})
    
    # 2. CAPA DE VELOCIDAD (Botones)
    mensaje_norm = mensaje.lower()
    mapeo_rapido = {
        "precio": "precios", "cuanto": "precios", "costo": "precios",
        "pedido": "pedido", "comprar": "pedido",
        "natural": "natural", "crianza": "natural", "crían": "natural",
        "origen": "origen", "dónde": "origen", "coroico": "origen",
        "entrega": "entrega", "delivery": "entrega", "zona": "entrega",
        "pack": "pack"
    }

    for palabra_clave, clave_local in mapeo_rapido.items():
        if palabra_clave in mensaje_norm:
            respuesta_texto = responder_local(clave_local)
            historial = session.get("historial", [])
            historial.append({"rol": "usuario", "contenido": mensaje})
            historial.append({"rol": "asistente", "contenido": respuesta_texto})
            session["historial"] = historial[-10:]
            session.modified = True
            return jsonify({"ok": True, "response": respuesta_texto, "motor": "local-rapido"})

    # 3. CAPA DE INTELIGENCIA (Ollama)
    historial = session.get("historial", [])
    try:
        respuesta_texto = _llamar_ollama(mensaje, historial)
        motor_usado = "ollama"
    except Exception as e:
        logger.error(f"Error en Ollama: {e}")
        respuesta_texto = responder_local(mensaje)
        motor_usado = "local-fallo"
    
    historial.append({"rol": "usuario", "contenido": mensaje})
    historial.append({"rol": "asistente", "contenido": respuesta_texto})
    session["historial"] = historial[-10:]
    session.modified = True

    return jsonify({"ok": True, "response": respuesta_texto, "motor": motor_usado})
# ... (aquí termina tu función chat)

def guardar_lead(nombre, telefono):
    """
    Guarda los datos del cliente en un archivo de texto de forma segura.
    """
    try:
        with open("leads_clientes.txt", "a", encoding="utf-8") as f:
            f.write(f"Nombre: {nombre} | WhatsApp: {telefono}\n")
    except Exception as e:
        print(f"Error al guardar el lead: {e}")

@app.route("/chat/limpiar", methods=["POST"])
def chat_limpiar():
    """Borra el historial de conversación de la sesión actual."""
    session.pop("historial", None)
    session.modified = True
    return jsonify({"ok": True, "mensaje": "Historial borrado."})


@app.route("/chat/estado")
def chat_estado():
    """Health-check del chatbot."""
    return jsonify({
        "ollama_activo":   _ollama_disponible(),
        "modelo":          OLLAMA_MODEL,
        "base_url":        OLLAMA_BASE_URL,
        "mensajes_sesion": len(session.get("historial", [])),
    })


# ─────────────────────────────────────────
#  Modo consola  →  python chatbot.py
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--server" in sys.argv or "--run" in sys.argv:
        port = int(os.environ.get("PORT", 5000))
        logger.info("Iniciando servidor en http://0.0.0.0:%d", port)
        app.run(host="0.0.0.0", port=port, debug=True, use_reloader=True)
    else:
        # Modo consola interactivo — comportamiento original conservado
        motor_str = (
            f"Ollama ({OLLAMA_MODEL})" if _ollama_disponible()
            else "Reglas locales (Ollama no disponible)"
        )
        print("=" * 56)
        print("  🐔  Avi – Asistente Virtual de Origen Avicor")
        print(f"  Motor: {motor_str}")
        print("  Escribe 'salir' para terminar.")
        print("=" * 56)

        historial_consola: list = []

        while True:
            try:
                entrada = input("\nVos : ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAvi: ¡Hasta luego! 👋")
                break

            if not entrada:
                continue

            if normalizar(entrada) in ("salir", "exit", "quit"):
                print("Avi: ¡Hasta pronto! 👋 Fue un placer asesorarte.")
                break

            r = _obtener_respuesta(entrada, historial_consola)
            historial_consola.append({"rol": "usuario",   "contenido": entrada})
            historial_consola.append({"rol": "asistente", "contenido": r})
            print(f"Avi: {r}")