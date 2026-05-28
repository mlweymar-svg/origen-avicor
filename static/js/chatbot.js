// chatbot.js – Asesor Virtual Avi · Origen Avicor
// Estructura y base de conocimiento originales conservadas íntegramente.
//
// MEJORAS sobre la versión original:
//   - Envío via fetch() a Flask POST /chat (motor Ollama/local)
//   - Fallback al motor de reglas local si el servidor no responde
//   - Indicador "escribiendo..." animado mientras espera respuesta
//   - Scroll automático al último mensaje
//   - Manejo robusto de errores de red con mensaje claro al usuario
//   - Limpieza automática del input tras enviar
//   - Funciones organizadas en módulos claros
//   - Estado del flujo de pedido conservado
//
// Datos del negocio (actualizados a Origen Avicor):
//   Pollo Entero      : Bs. 65 / unidad (~2.2 kg)
//   Pollo Orgánico    : Bs. 80 / unidad (~2.5 kg)
//   Pechuga fileteada : Bs. 48 / 500 g
//   Pack Familiar     : Bs. 145 (-15%)
//   Pack Parrillero   : Bs. 115
//   Pack Semanal      : Bs. 95 (-12%)
//   Envío gratis      : pedidos >= Bs. 120

// ─────────────────────────────────────────
//  Configuración
// ─────────────────────────────────────────

const CONFIG = {
  endpoint:         "/chat",          // ruta Flask POST /chat
  endpointLimpiar:  "/chat/limpiar",  // ruta para borrar historial
  usarServidor:     true,             // false = fuerza motor local siempre
  timeoutMs:        50000,            // timeout fetch en ms
  demoraBotMs:      420,              // pausa antes de mostrar respuesta local
  maxLongitudMsg:   800,              // caracteres máximos por mensaje
};

// ─────────────────────────────────────────
//  Estado del flujo de pedido (conservado original)
// ─────────────────────────────────────────

const estado = {
  paso:      null, // null | 'producto' | 'cantidad' | 'nombre' | 'direccion' | 'confirmar'
  producto:  null,
  cantidad:  null,
  nombre:    null,
  direccion: null,
};

const PRODUCTOS = {
  "pollo entero": { precio: 65,  unidad: "unidad", label: "Pollo Entero Avicor" },
  "entero":       { precio: 65,  unidad: "unidad", label: "Pollo Entero Avicor" },
  "organico":     { precio: 80,  unidad: "unidad", label: "Pollo Orgánico Certificado" },
  "organica":     { precio: 80,  unidad: "unidad", label: "Pollo Orgánico Certificado" },
  "pechuga":      { precio: 48,  unidad: "500 g",  label: "Pechuga Fileteada" },
  "presas":       { precio: 48,  unidad: "500 g",  label: "Pechuga Fileteada" },
  "presa":        { precio: 48,  unidad: "500 g",  label: "Pechuga Fileteada" },
  "muslo":        { precio: 38,  unidad: "pack x4", label: "Muslos Sazonados" },
  "muslos":       { precio: 38,  unidad: "pack x4", label: "Muslos Sazonados" },
  "pierna":       { precio: 32,  unidad: "500 g",  label: "Piernas con Hueso" },
  "piernas":      { precio: 32,  unidad: "500 g",  label: "Piernas con Hueso" },
  "pack familiar":{ precio: 145, unidad: "pack",   label: "Pack Familiar Completo" },
  "familiar":     { precio: 145, unidad: "pack",   label: "Pack Familiar Completo" },
  "parrillero":   { precio: 115, unidad: "pack",   label: "Pack Parrillero" },
  "semanal":      { precio: 95,  unidad: "pack",   label: "Pack Semanal Económico" },
};

// ─────────────────────────────────────────
//  Utilidades
// ─────────────────────────────────────────

/** Normaliza texto: minúsculas sin tildes. */
function normalizarTexto(texto) {
  return texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

/** Selecciona un elemento aleatorio de un array. */
function aleatorio(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

/** Formatea número con símbolo Bs. */
function formatearPrecio(num) {
  return `Bs. ${num}`;
}

// ─────────────────────────────────────────
//  Base de conocimiento local (original conservada)
// ─────────────────────────────────────────

const REGLAS = [

  // ── SALUDO ──
  {
    claves: ["hola", "buenas", "buenos", "saludos", "hey", "hi",
             "que tal", "como estas", "ola", "buen dia", "buen tarde"],
    respuestas: [
      "¡Hola! 👋 Soy Avi, el asistente de Origen Avicor. " +
      "Puedo ayudarte con precios, pedidos y nuestro origen en Coroico. ¿Qué necesitás?",

      "¡Buenas! 🐔 Soy Avi de Origen Avicor. Preguntame sobre productos, precios " +
      "o cómo hacer tu pedido. ¡Estoy aquí!",

      "¡Hola! Me alegra que estés aquí. Soy tu asistente virtual de Origen Avicor. " +
      "¿En qué te puedo ayudar hoy?",
    ]
  },

  // ── PEDIDO (inicia el flujo) ──
  {
    claves: ["pedido", "pedir", "comprar", "quiero", "ordenar", "llevar",
             "encargar", "hacer pedido"],
    respuestas: ["__INICIAR_PEDIDO__"]
  },

  // ── PRECIOS ──
  {
    claves: ["precio", "cuanto", "costo", "vale", "valor",
             "bs", "bolivianos", "cuanto cuesta", "cuanto vale"],
    respuestas: [
      "💰 Nuestros precios actuales:\n" +
      "• Pollo entero: Bs. 65 (~2.2 kg)\n" +
      "• Pollo orgánico: Bs. 80 (~2.5 kg, QR trazable)\n" +
      "• Pechuga fileteada: Bs. 48 / 500 g\n" +
      "• Pack Familiar: Bs. 145 (ahorrás 15%)\n" +
      "• Pack Parrillero: Bs. 115\n" +
      "Envío gratis en pedidos ≥ Bs. 120. ¿Te interesa alguno?",

      "🐔 Precios Origen Avicor:\n" +
      "• Pollo Entero → Bs. 65\n" +
      "• Pollo Orgánico → Bs. 80\n" +
      "• Pechugas → Bs. 48 / 500 g\n" +
      "• Pack Familiar → Bs. 145 (-15%)\n" +
      "Todos frescos, sin hormonas, directo de Coroico.",
    ]
  },

  // ── BENEFICIOS / NATURAL / ORGÁNICO ──
  {
    claves: ["natural", "quimico", "hormona", "alimentacion", "crianza",
             "campo", "libre", "como crian", "organico", "organica",
             "sin antibiotico", "certificado", "beneficio", "diferencia", "por que"],
    respuestas: [
      "🌿 Crianza 100% natural en Coroico:\n" +
      "• Campo abierto, sin jaulas ni hacinamiento\n" +
      "• Alimentación: maíz criollo, quinua y hierbas silvestres\n" +
      "• Cero hormonas · Cero antibióticos preventivos\n" +
      "• Trazabilidad QR en cada empaque\n" +
      "• Empaque biodegradable al vacío\n" +
      "¡El sabor del campo boliviano en tu mesa!",

      "✅ ¿Por qué elegirnos?\n" +
      "• Productores directos de Coroico (sin intermediarios)\n" +
      "• Sin hormonas ni antibióticos — garantizado\n" +
      "• Más de 300 familias bolivianas confían en nosotros (4.9★)\n" +
      "¿Querés hacer un pedido?",
    ]
  },

  // ── ORIGEN COROICO ──
  {
    claves: ["coroico", "yungas", "origen", "donde", "ubicacion",
             "granja", "produce", "lugar", "estan"],
    respuestas: [
      "📍 Nuestras granjas están en Coroico, Yungas de La Paz, " +
      "a 1.700 msnm. Clima subtropical ideal (18–24°C), agua de vertiente " +
      "y campo abierto. Trabajamos con 12 familias productoras locales.",

      "Coroico, en los Yungas bolivianos 🌿. Producción propia, entrega directa " +
      "a La Paz. Sin intermediarios. Eso garantiza frescura y precio justo.",
    ]
  },

  // ── ENTREGA / ENVÍO ──
  {
    claves: ["entrega", "delivery", "envio", "llegar", "zona", "lleva",
             "domicilio", "reparto", "despacho", "cuantos dias",
             "cuando llega", "tiempo entrega", "demora"],
    respuestas: [
      "🚚 Entregamos en La Paz y alrededores:\n" +
      "• Lun–Sáb: 7:00 am – 6:00 pm\n" +
      "• Dom: 8:00 am – 2:00 pm\n" +
      "• Envío GRATIS en pedidos ≥ Bs. 120\n" +
      "Al hacer tu pedido te confirmamos el tiempo según tu zona. 📍",

      "Entregamos en La Paz con cadena de frío ininterrumpida. 🌿 " +
      "Gratis si tu pedido supera Bs. 120. ¿En qué zona estás?",
    ]
  },

  // ── CONTACTO / HORARIO ──
  {
    claves: ["contacto", "telefono", "whatsapp", "llamar", "numero",
             "comunicar", "escribir", "horario", "hora", "atienden"],
    respuestas: [
      "📞 Contacto Origen Avicor:\n" +
      "• WhatsApp/Tel: +591 79 000 000\n" +
      "• Email: hola@origenavicor.bo\n" +
      "• Horario: Lun–Sáb 7:00–18:00 · Dom 8:00–14:00",

      "¡Escribinos! 📱 +591 79 000 000 por WhatsApp o llamada. " +
      "Lun–Sáb de 7 a 18 hs. ¡Respuesta rápida garantizada!",
    ]
  },

  // ── PACK / COMBO ──
  {
    claves: ["pack", "combo", "familiar", "parrillero", "semanal", "ahorro"],
    respuestas: [
      "🎁 Nuestros packs con descuento:\n" +
      "• Pack Familiar → Bs. 145 (antes Bs. 170, -15%)\n" +
      "  Incluye: pollo entero + 1 kg pechugas + ½ kg muslos\n" +
      "• Pack Parrillero → Bs. 115 (para 4–6 personas)\n" +
      "• Pack Semanal Económico → Bs. 95 (-12%)\n" +
      "¿Cuál se adapta mejor a vos?",
    ]
  },

  // ── RECOMENDACIÓN ──
  {
    claves: ["recomienda", "cual es mejor", "cual compro",
             "para familia", "para evento", "para dieta", "para restaurante"],
    respuestas: [
      "💡 Te asesoro según tu necesidad:\n" +
      "• Familia (4–6 personas) → Pack Familiar (Bs. 145)\n" +
      "• Evento o reunión → Pack Parrillero (Bs. 115)\n" +
      "• Dieta o salud → Pollo Orgánico Certificado (Bs. 80)\n" +
      "• Presupuesto ajustado → Pack Semanal (Bs. 95)\n" +
      "¿Cuál se adapta mejor a vos?",
    ]
  },

  // ── DESCUENTO / OFERTA ──
  {
    claves: ["descuento", "oferta", "promocion", "barato",
             "precio especial", "rebaja", "convenio"],
    respuestas: [
      "🎁 Los packs ya incluyen descuentos de hasta 15%. " +
      "Para pedidos corporativos, escribinos al +591 79 000 000.",

      "💰 Si querés aprovechar al máximo, optá por nuestros packs. ¿Te paso los precios?",
    ]
  },

  // ── RECETAS ──
  {
    claves: ["receta", "preparar", "cocinar", "cocina",
             "como hacer", "sopa", "asado", "frito", "guiso"],
    respuestas: [
      "👨‍🍳 ¡Con pollo de campo el resultado siempre es mejor!\n" +
      "• Asado o parrilla → Pollo Entero (Bs. 65)\n" +
      "• Sopa o guiso → Piernas con hueso (Bs. 32)\n" +
      "• Dieta fitness → Pechuga fileteada\n" +
      "¿Te ayudo a elegir el corte ideal?",
    ]
  },

  // ── GRACIAS ──
  {
    claves: ["gracias", "muchas gracias", "genial", "perfecto",
             "excelente", "buenisimo", "ok", "listo", "entendido"],
    respuestas: [
      "¡De nada! 😊 Si querés hacer un pedido o tenés más preguntas, aquí estoy.",
      "¡Con gusto! 🐔 ¿Hay algo más en lo que pueda ayudarte?",
      "¡Fue un placer asesorarte! 🌿 ¿Hay algo más?",
    ]
  },

  // ── DESPEDIDA ──
  {
    claves: ["adios", "chau", "bye", "hasta luego", "nos vemos", "ciao"],
    respuestas: [
      "¡Hasta pronto! 👋 Fue un placer asesorarte. ¡Volvé cuando quieras pedir!",
      "¡Nos vemos! 🐔 Cualquier consulta o pedido, aquí estaré.",
    ]
  },
];

const RESPUESTAS_DEFAULT = [
  "¡Claro! 🐔 Vendemos pollo natural de Coroico: entero, orgánico y cortes especiales. ¿Te gustaría conocer los precios de hoy o cómo hacer un pedido?",

  "Para esa consulta específica, te sugiero hablar directamente con un humano por WhatsApp aquí: +591 79 000 000. 📲 ¡Estamos listos para atenderte!",

  "No estoy seguro de eso, pero recuerda que tenemos envíos gratis en pedidos mayores a Bs. 120. 🚚 ¿Quieres que te muestre nuestros Packs Familiares?",
];

// ─────────────────────────────────────────
//  Flujo de pedido paso a paso (conservado original)
// ─────────────────────────────────────────

function manejarPedido(texto) {
  const t = normalizarTexto(texto);

  // ── PASO: elegir producto ──
  if (estado.paso === "producto") {
    for (const clave of Object.keys(PRODUCTOS)) {
      if (t.includes(normalizarTexto(clave))) {
        estado.producto = PRODUCTOS[clave];
        estado.paso = "cantidad";
        return (
          `Perfecto, elegiste ${estado.producto.label} a ${formatearPrecio(estado.producto.precio)} / ${estado.producto.unidad}. 🐔\n` +
          `¿Cuántas unidades / packs necesitás? (mínimo 1, máximo 10)`
        );
      }
    }
    return (
      "No reconocí ese producto. 🤔 Elegí uno:\n" +
      "• Pollo Entero (Bs. 65)\n" +
      "• Pollo Orgánico (Bs. 80)\n" +
      "• Pechuga Fileteada (Bs. 48 / 500 g)\n" +
      "• Pack Familiar (Bs. 145)\n" +
      "• Pack Parrillero (Bs. 115)"
    );
  }

  // ── PASO: elegir cantidad ──
  if (estado.paso === "cantidad") {
    const num = parseInt(t.match(/\d+/)?.[0]);
    if (!num || num < 1 || num > 10) {
      return "La cantidad debe estar entre 1 y 10. ¿Cuánto necesitás?";
    }
    estado.cantidad = num;
    estado.paso = "nombre";
    const total = num * estado.producto.precio;
    return (
      `Anotado: ${num} x ${estado.producto.label} → Total: ${formatearPrecio(total)} 💰\n\n` +
      `¿Cuál es tu nombre para el pedido?`
    );
  }

  // ── PASO: nombre ──
  if (estado.paso === "nombre") {
    if (t.length < 2) return "Por favor escribí tu nombre para continuar.";
    estado.nombre = texto.trim();
    estado.paso = "direccion";
    return `Gracias, ${estado.nombre}. 😊 ¿Cuál es tu zona o dirección de entrega en La Paz?`;
  }

  // ── PASO: dirección ──
  if (estado.paso === "direccion") {
    if (t.length < 3) return "Por favor indicá tu zona con un poco más de detalle.";
    estado.direccion = texto.trim();
    estado.paso = "confirmar";
    const total = estado.cantidad * estado.producto.precio;
    const envio = total >= 120 ? "¡Gratis! 🎉" : "Bs. 12";
    return (
      `📋 Resumen de tu pedido:\n` +
      `• Producto:  ${estado.producto.label}\n` +
      `• Cantidad:  ${estado.cantidad}\n` +
      `• Subtotal:  ${formatearPrecio(total)}\n` +
      `• Envío:     ${envio}\n` +
      `• Nombre:    ${estado.nombre}\n` +
      `• Zona:      ${estado.direccion}\n\n` +
      `¿Confirmamos el pedido? Escribí "sí" para confirmar o "no" para cancelar.`
    );
  }

  // ── PASO: confirmar ──
  if (estado.paso === "confirmar") {
    const siConfirma = ["si", "sí", "s", "confirmo", "ok", "dale", "vamos"].some(w => t.includes(w));
    const noConfirma = ["no", "cancel", "nope", "cancelar"].some(w => t.includes(w));

    if (siConfirma) {
      const total = estado.cantidad * estado.producto.precio;
      const envio = total >= 120 ? 0 : 12;
      const totalFinal = total + envio;
      const resumen =
        `✅ ¡Pedido registrado con éxito!\n` +
        `• ${estado.cantidad} x ${estado.producto.label}\n` +
        `• Subtotal: ${formatearPrecio(total)}\n` +
        `• Envío: ${envio === 0 ? "Gratis 🎉" : formatearPrecio(envio)}\n` +
        `• TOTAL: ${formatearPrecio(totalFinal)}\n` +
        `• Para: ${estado.nombre}\n` +
        `• Entrega en: ${estado.direccion}\n\n` +
        `Nos pondremos en contacto pronto para coordinar. ¡Gracias por elegirnos! 🐔🌿`;
      _resetearEstado();
      return resumen;
    }

    if (noConfirma) {
      _resetearEstado();
      return "Pedido cancelado. 😊 Si cambiás de opinión, escribí 'quiero hacer un pedido' cuando quieras.";
    }

    return "¿Confirmamos el pedido? Escribí \"sí\" para confirmar o \"no\" para cancelar.";
  }

  return null; // no estamos en flujo de pedido
}

function _resetearEstado() {
  Object.assign(estado, { paso: null, producto: null, cantidad: null, nombre: null, direccion: null });
}

// ─────────────────────────────────────────
//  Motor de respuesta local (conservado original)
// ─────────────────────────────────────────

function responderLocal(mensaje) {
  const t = normalizarTexto(mensaje);

  // Si hay un flujo de pedido activo, tiene prioridad
  if (estado.paso !== null) {
    const respuestaPedido = manejarPedido(mensaje);
    if (respuestaPedido !== null) return respuestaPedido;
  }

  // Buscar en base de conocimiento
  for (const regla of REGLAS) {
    const coincide = regla.claves.some(c => t.includes(normalizarTexto(c)));
    if (coincide) {
      const r = aleatorio(regla.respuestas);

      if (r === "__INICIAR_PEDIDO__") {
        estado.paso = "producto";
        return (
          "¡Perfecto! 🛒 Vamos a tomar tu pedido paso a paso.\n\n" +
          "¿Qué producto deseás?\n" +
          "• Pollo Entero (Bs. 65 / ~2.2 kg)\n" +
          "• Pollo Orgánico (Bs. 80 / ~2.5 kg)\n" +
          "• Pechuga Fileteada (Bs. 48 / 500 g)\n" +
          "• Pack Familiar (Bs. 145)\n" +
          "• Pack Parrillero (Bs. 115)"
        );
      }

      return r;
    }
  }

  return aleatorio(RESPUESTAS_DEFAULT);
}

// ─────────────────────────────────────────
//  Comunicación con Flask /chat
// ─────────────────────────────────────────

/**
 * Envía el mensaje al servidor Flask y retorna la respuesta.
 * En caso de error de red, hace fallback al motor local.
 * @param {string} mensaje
 * @returns {Promise<string>}
 */
async function obtenerRespuesta(mensaje) {
  if (!CONFIG.usarServidor) {
    return responderLocal(mensaje);
  }

  try {
    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), CONFIG.timeoutMs);

    const resp = await fetch(CONFIG.endpoint, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ mensaje }),
      signal:  controller.signal,
    });

    clearTimeout(timeoutId);

    if (!resp.ok) {
      console.warn(`[chatbot] Servidor devolvió HTTP ${resp.status}. Usando motor local.`);
      return responderLocal(mensaje);
    }

    const datos = await resp.json();

    if (!datos.ok || !datos.respuesta) {
      console.warn("[chatbot] Respuesta del servidor inválida. Usando motor local.");
      return responderLocal(mensaje);
    }

    return datos.respuesta;

  } catch (err) {
    if (err.name === "AbortError") {
      console.warn("[chatbot] Timeout de red. Usando motor local.");
    } else {
      console.warn("[chatbot] Error de red:", err.message, ". Usando motor local.");
    }
    return responderLocal(mensaje);
  }
}

// ─────────────────────────────────────────
//  UI del chat
// ─────────────────────────────────────────

/**
 * Agrega una burbuja de mensaje al área de chat.
 * @param {string} texto
 * @param {boolean} esBot
 */
function agregarMensaje(texto, esBot) {
  const chat = document.getElementById("chat");
  if (!chat) return;

  const div = document.createElement("div");
  div.className = "msg " + (esBot ? "msg--bot" : "msg--user");
  div.style.whiteSpace = "pre-line";
  div.textContent = texto;

  // Animación de entrada
  div.style.opacity = "0";
  div.style.transform = esBot ? "translateX(-8px)" : "translateX(8px)";
  div.style.transition = "opacity 0.22s ease, transform 0.22s ease";

  chat.appendChild(div);

  // Forzar reflow para que la transición funcione
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      div.style.opacity = "1";
      div.style.transform = "translateX(0)";
    });
  });

  scrollAlFinal(chat);
  return div;
}

/**
 * Muestra el indicador "escribiendo..." y retorna una función para ocultarlo.
 * @returns {{ el: HTMLElement, ocultar: Function }}
 */
function mostrarEscribiendo() {
  const chat = document.getElementById("chat");
  if (!chat) return { el: null, ocultar: () => {} };

  const div = document.createElement("div");
  div.className = "msg msg--bot msg--typing";
  div.setAttribute("aria-label", "El asistente está escribiendo");
  div.innerHTML =
    '<span class="typing-dot"></span>' +
    '<span class="typing-dot"></span>' +
    '<span class="typing-dot"></span>';

  chat.appendChild(div);
  scrollAlFinal(chat);

  return {
    el: div,
    ocultar: () => { if (div.parentNode) div.parentNode.removeChild(div); },
  };
}

/** Scroll suave al final del área de chat. */
function scrollAlFinal(chat) {
  const el = chat || document.getElementById("chat");
  if (el) {
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }
}

/** Deshabilita / habilita el input y el botón de envío. */
function setInputHabilitado(habilitado) {
  const input = document.getElementById("mensaje");
  const boton = document.getElementById("btn-enviar") ||
                document.querySelector(".chatbot__send");
  if (input) input.disabled = !habilitado;
  if (boton) boton.disabled = !habilitado;
}

// ─────────────────────────────────────────
//  Función enviar (mejorada)
// ─────────────────────────────────────────

let enviando = false; // previene doble-envío

async function enviar() {
  if (enviando) return;

  const input = document.getElementById("mensaje");
  if (!input) return;

  const texto = input.value.trim().slice(0, CONFIG.maxLongitudMsg);
  if (!texto) return;

  // Mostrar mensaje del usuario
  agregarMensaje(texto, false);
  input.value = "";

  // Bloquear UI mientras espera respuesta
  enviando = true;
  setInputHabilitado(false);

  // Mostrar indicador "escribiendo..."
  const typing = mostrarEscribiendo();

  try {
    const respuesta = await obtenerRespuesta(texto);
    typing.ocultar();
    agregarMensaje(respuesta, true);
  } catch (err) {
    typing.ocultar();
    agregarMensaje(
      "Lo siento, tuve un problema al procesar tu consulta. " +
      "Escribinos al WhatsApp +591 79 000 000. 🐔",
      true,
    );
    console.error("[chatbot] Error inesperado:", err);
  } finally {
    enviando = false;
    setInputHabilitado(true);
    const inputFinal = document.getElementById("mensaje");
    if (inputFinal) inputFinal.focus();
  }
}

// ─────────────────────────────────────────
//  Limpiar historial del chat
// ─────────────────────────────────────────

async function limpiarChat() {
  const chat = document.getElementById("chat");
  if (!chat) return;

  // Vaciar DOM del chat
  while (chat.firstChild) chat.removeChild(chat.firstChild);

  // Resetear flujo de pedido
  _resetearEstado();

  // Limpiar sesión en el servidor (si está disponible)
  if (CONFIG.usarServidor) {
    try {
      await fetch(CONFIG.endpointLimpiar, { method: "POST" });
    } catch (_) {
      // No crítico si falla
    }
  }

  // Mensaje de bienvenida inicial
  setTimeout(() => {
    agregarMensaje(
      "¡Chat reiniciado! 👋 Soy Avi, el asistente de Origen Avicor. " +
      "¿En qué te puedo ayudar?",
      true,
    );
  }, 150);
}

// ─────────────────────────────────────────
//  Inicialización
// ─────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("mensaje");

  // Enviar con Enter (sin Shift)
  if (input) {
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        enviar();
      }
    });

    // Auto-resize si es textarea
    if (input.tagName === "TEXTAREA") {
      input.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 120) + "px";
      });
    }

    // Foco inicial
    input.focus();
  }

  // Botón limpiar (si existe en el HTML)
  const btnLimpiar = document.getElementById("btn-limpiar");
  if (btnLimpiar) {
    btnLimpiar.addEventListener("click", limpiarChat);
  }

  // Botón de envío alternativo con id btn-enviar
  const btnEnviar = document.getElementById("btn-enviar");
  if (btnEnviar) {
    btnEnviar.addEventListener("click", enviar);
  }

  // Scroll al final al cargar
  scrollAlFinal();

  console.log(
    "%c🐔 Chatbot Avi — Origen Avicor",
    "color:#556B2F;font-weight:bold;font-size:13px",
  );
  console.log(
    "%cMotor: fetch → /api/chat (Ollama/llama3) con fallback local.",
    "color:#D68A5E",
  );
});
// --- FUNCIONES PARA QUE TUS BOTONES FUNCIONEN ---

function enviar() {
  const input = document.getElementById("mensaje") || 
                document.getElementById("chat-input") || 
                document.querySelector("textarea");
  
  if (!input) {
      console.error("No se encontró el cuadro de texto en el HTML");
      return;
  }

  const mensaje = input.value.trim();
  if (mensaje !== "") {
    // 1. Esto muestra TU mensaje en la pantalla inmediatamente
    if (typeof agregarMensaje === "function") {
        agregarMensaje(mensaje, false); // false para que salga como usuario
    }

    console.log("Enviando mensaje:", mensaje);

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: mensaje }),
    })
      .then((response) => response.json())
      .then((data) => {
        // CORRECCIÓN FINAL: Acepta cualquier nombre que mande Python
        const respuestaIA = data.response || data.reply || data.answer;
        
        if (typeof agregarMensaje === "function") {
            agregarMensaje(respuestaIA, true); 
        }
        
        console.log("Respuesta de Avi:", respuestaIA);
        input.value = ""; 
      })
      .catch((error) => console.error("Error en el chat:", error));
  }
}
// Esta función es la que usan los botones de "Precios", "Entrega", etc.
function enviarChip(texto) {
  const input = document.getElementById("chat-input") || document.querySelector(".chatbot__input textarea");
  if (input) {
    input.value = texto;
    enviar(); // Llama a la función de arriba automáticamente
  }
}

// Esta es para los botones de "Pedir" de la página de productos
function iniciarPedidoChat(producto) {
  const input = document.getElementById("chat-input") || document.querySelector(".chatbot__input textarea");
  if (input) {
    input.value = "Hola, quiero pedir un " + producto;
    enviar();
  }
}