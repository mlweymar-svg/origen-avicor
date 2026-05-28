# ==============================================================================
#  ORIGEN AVICOR — pedidos.py
#  Módulo de gestión de pedidos
#
#  Responsabilidades:
#    - Crear y validar pedidos
#    - Persistir pedidos en archivo JSON
#    - Listar y buscar pedidos
#    - Simular el flujo completo de compra (pendiente → confirmado → entregado)
#    - Generar resúmenes y estadísticas básicas
#
#  Uso desde app.py:
#      from pedidos import GestorPedidos, crear_pedido, listar_pedidos
#
#  Uso directo (demo/test):
#      python pedidos.py
# ==============================================================================

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ==============================================================================
#  1. LOGGING
# ==============================================================================

logger = logging.getLogger("avicor.pedidos")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  pedidos — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_handler)


# ==============================================================================
#  2. CONFIGURACIÓN
# ==============================================================================

# Ruta al archivo JSON donde se persisten los pedidos
PEDIDOS_JSON: Path = Path(
    os.environ.get("PEDIDOS_JSON_PATH", "data/pedidos.json")
)

# Carpeta de datos (se crea automáticamente si no existe)
PEDIDOS_JSON.parent.mkdir(parents=True, exist_ok=True)

# Precio de envío estándar (Bs.)
PRECIO_ENVIO:        float = 12.0
UMBRAL_ENVIO_GRATIS: float = 120.0   # pedidos >= a este monto → envío gratis

# Estados válidos del ciclo de vida de un pedido
ESTADOS_VALIDOS: tuple[str, ...] = (
    "pendiente",    # recién creado, aún no confirmado
    "confirmado",   # operador lo confirmó / pago verificado
    "en_camino",    # salió de la granja hacia La Paz
    "entregado",    # el cliente lo recibió
    "cancelado",    # cancelado por el cliente o por Avicor
)

# Transiciones permitidas entre estados
TRANSICIONES: dict[str, list[str]] = {
    "pendiente":  ["confirmado", "cancelado"],
    "confirmado": ["en_camino",  "cancelado"],
    "en_camino":  ["entregado",  "cancelado"],
    "entregado":  [],        # estado final exitoso
    "cancelado":  [],        # estado final cancelado
}

# Catálogo de productos con precios (espejo del catálogo en app.py)
CATALOGO: dict[int, dict] = {
    1:  {"nombre": "Pollo entero Avicor",          "precio": 65.00,  "unidad": "unidad"},
    2:  {"nombre": "Pechuga fileteada",             "precio": 48.00,  "unidad": "500 g"},
    3:  {"nombre": "Pack Familiar Completo",        "precio": 145.00, "unidad": "pack"},
    4:  {"nombre": "Muslos sazonados",              "precio": 38.00,  "unidad": "pack x4"},
    5:  {"nombre": "Piernas con hueso",             "precio": 32.00,  "unidad": "500 g"},
    6:  {"nombre": "Pollo orgánico certificado",    "precio": 80.00,  "unidad": "unidad"},
    7:  {"nombre": "Menudencias mix",               "precio": 18.00,  "unidad": "300 g"},
    8:  {"nombre": "Hígado de pollo fresco",        "precio": 15.00,  "unidad": "250 g"},
    9:  {"nombre": "Pack Parrillero",               "precio": 115.00, "unidad": "pack"},
    10: {"nombre": "Pack Semanal Económico",        "precio": 95.00,  "unidad": "pack"},
    11: {"nombre": "Pechuga entera con hueso 1 kg", "precio": 55.00,  "unidad": "1 kg"},
    12: {"nombre": "Pollo entero pequeño",          "precio": 52.00,  "unidad": "unidad"},
}


# ==============================================================================
#  3. DATACLASSES — Modelos de datos
# ==============================================================================

@dataclass
class ItemPedido:
    """Un renglón del pedido: qué producto, cuántas unidades y a qué precio."""
    producto_id:     int
    nombre_producto: str
    precio_unitario: float
    cantidad:        int
    subtotal:        float = field(init=False)

    def __post_init__(self) -> None:
        self.subtotal = round(self.precio_unitario * self.cantidad, 2)

    def a_dict(self) -> dict:
        return {
            "producto_id":     self.producto_id,
            "nombre_producto": self.nombre_producto,
            "precio_unitario": self.precio_unitario,
            "cantidad":        self.cantidad,
            "subtotal":        self.subtotal,
        }


@dataclass
class Pedido:
    """
    Representa un pedido completo de Origen Avicor.

    Campos calculados automáticamente:
        subtotal_bs, envio_bs, total_bs
    """
    # Identificación
    id:          str = field(default_factory=lambda: _generar_id())
    numero:      str = field(default="")       # ej: "AVN-20240601-0001"

    # Datos del cliente
    cliente_nombre:   str = ""
    cliente_telefono: str = ""
    cliente_zona:     str = ""
    cliente_email:    str = ""

    # Contenido del pedido
    items: list[ItemPedido] = field(default_factory=list)
    notas: str = ""

    # Montos
    subtotal_bs: float = field(default=0.0)
    envio_bs:    float = field(default=0.0)
    total_bs:    float = field(default=0.0)

    # Estado y ciclo de vida
    estado:       str = "pendiente"
    historial_estados: list[dict] = field(default_factory=list)

    # Metadatos
    creado_en:     str = field(default_factory=lambda: datetime.now().isoformat())
    actualizado_en: str = field(default_factory=lambda: datetime.now().isoformat())
    usuario_id:    int | None = None

    def __post_init__(self) -> None:
        self._recalcular_totales()
        if not self.numero:
            self.numero = _generar_numero(self.creado_en)
        if not self.historial_estados:
            self.historial_estados = [_evento_estado("pendiente", "Pedido creado")]

    # ------------------------------------------------------------------

    def _recalcular_totales(self) -> None:
        """Calcula subtotal, envío y total a partir de los ítems."""
        self.subtotal_bs = round(
            sum(item.subtotal for item in self.items), 2
        )
        self.envio_bs = (
            0.0 if self.subtotal_bs >= UMBRAL_ENVIO_GRATIS
            else PRECIO_ENVIO
        )
        self.total_bs = round(self.subtotal_bs + self.envio_bs, 2)

    def agregar_item(self, item: ItemPedido) -> None:
        """Agrega un ítem al pedido y recalcula los totales."""
        self.items.append(item)
        self._recalcular_totales()
        self.actualizado_en = datetime.now().isoformat()

    def cambiar_estado(self, nuevo_estado: str, nota: str = "") -> None:
        """
        Cambia el estado del pedido si la transición es válida.
        Lanza PedidoError si la transición no está permitida.
        """
        if nuevo_estado not in ESTADOS_VALIDOS:
            raise PedidoError(
                f"Estado '{nuevo_estado}' no es válido. "
                f"Estados válidos: {ESTADOS_VALIDOS}"
            )
        permitidos = TRANSICIONES.get(self.estado, [])
        if nuevo_estado not in permitidos:
            raise PedidoError(
                f"No se puede pasar de '{self.estado}' a '{nuevo_estado}'. "
                f"Transiciones permitidas: {permitidos or ['ninguna']}"
            )
        self.estado = nuevo_estado
        self.historial_estados.append(
            _evento_estado(nuevo_estado, nota or f"Estado cambiado a {nuevo_estado}")
        )
        self.actualizado_en = datetime.now().isoformat()
        logger.info("Pedido %s → estado: %s", self.numero, nuevo_estado)

    def esta_activo(self) -> bool:
        """True si el pedido no está en un estado final."""
        return self.estado not in ("entregado", "cancelado")

    def resumen(self) -> str:
        """Devuelve una representación de texto legible del pedido."""
        lineas = [
            f"{'─' * 50}",
            f"  PEDIDO {self.numero}",
            f"{'─' * 50}",
            f"  Cliente:  {self.cliente_nombre}",
            f"  Teléfono: {self.cliente_telefono}",
            f"  Zona:     {self.cliente_zona}",
            f"  Estado:   {self.estado.upper()}",
            f"  Creado:   {self.creado_en[:19]}",
            f"{'─' * 50}",
            f"  ÍTEMS:",
        ]
        for item in self.items:
            lineas.append(
                f"    • {item.nombre_producto:<35} "
                f"x{item.cantidad}  Bs. {item.subtotal:.2f}"
            )
        lineas += [
            f"{'─' * 50}",
            f"  Subtotal: Bs. {self.subtotal_bs:.2f}",
            f"  Envío:    {'Gratis 🎉' if self.envio_bs == 0 else f'Bs. {self.envio_bs:.2f}'}",
            f"  TOTAL:    Bs. {self.total_bs:.2f}",
        ]
        if self.notas:
            lineas.append(f"  Notas:    {self.notas}")
        lineas.append(f"{'─' * 50}")
        return "\n".join(lineas)

    def a_dict(self) -> dict:
        """Serializa el pedido a dict (compatible con JSON)."""
        return {
            "id":                self.id,
            "numero":            self.numero,
            "cliente_nombre":    self.cliente_nombre,
            "cliente_telefono":  self.cliente_telefono,
            "cliente_zona":      self.cliente_zona,
            "cliente_email":     self.cliente_email,
            "items":             [item.a_dict() for item in self.items],
            "notas":             self.notas,
            "subtotal_bs":       self.subtotal_bs,
            "envio_bs":          self.envio_bs,
            "total_bs":          self.total_bs,
            "estado":            self.estado,
            "historial_estados": self.historial_estados,
            "creado_en":         self.creado_en,
            "actualizado_en":    self.actualizado_en,
            "usuario_id":        self.usuario_id,
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> "Pedido":
        """Reconstruye un Pedido a partir de un dict (leído del JSON)."""
        items = [
            ItemPedido(
                producto_id=     i["producto_id"],
                nombre_producto= i["nombre_producto"],
                precio_unitario= i["precio_unitario"],
                cantidad=        i["cantidad"],
            )
            for i in datos.get("items", [])
        ]
        pedido = cls(
            id=               datos["id"],
            numero=           datos["numero"],
            cliente_nombre=   datos.get("cliente_nombre", ""),
            cliente_telefono= datos.get("cliente_telefono", ""),
            cliente_zona=     datos.get("cliente_zona", ""),
            cliente_email=    datos.get("cliente_email", ""),
            items=            items,
            notas=            datos.get("notas", ""),
            estado=           datos.get("estado", "pendiente"),
            historial_estados=datos.get("historial_estados", []),
            creado_en=        datos.get("creado_en", datetime.now().isoformat()),
            actualizado_en=   datos.get("actualizado_en", datetime.now().isoformat()),
            usuario_id=       datos.get("usuario_id"),
        )
        # Sobreescribir totales desde el JSON guardado (no recalcular)
        pedido.subtotal_bs = datos.get("subtotal_bs", pedido.subtotal_bs)
        pedido.envio_bs    = datos.get("envio_bs",    pedido.envio_bs)
        pedido.total_bs    = datos.get("total_bs",    pedido.total_bs)
        return pedido


# ==============================================================================
#  4. EXCEPCIÓN PERSONALIZADA
# ==============================================================================

class PedidoError(Exception):
    """Error de negocio relacionado con la creación o gestión de pedidos."""
    pass


# ==============================================================================
#  5. GESTOR DE PEDIDOS — Clase principal
# ==============================================================================

class GestorPedidos:
    """
    Gestiona el ciclo de vida completo de los pedidos de Origen Avicor.

    Persiste en un archivo JSON local (PEDIDOS_JSON).
    En producción, reemplazar los métodos _cargar / _guardar
    por operaciones a una base de datos (SQLAlchemy, PostgreSQL, etc.).

    Uso básico:
        gestor = GestorPedidos()

        pedido = gestor.crear_pedido(
            cliente_nombre="María García",
            cliente_telefono="+591 76543210",
            cliente_zona="Miraflores",
            items=[{"producto_id": 1, "cantidad": 2}]
        )

        gestor.confirmar_pedido(pedido.numero)
        todos = gestor.listar_pedidos()
    """

    def __init__(self, ruta_json: Path = PEDIDOS_JSON) -> None:
        self._ruta = ruta_json
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        logger.info("GestorPedidos inicializado — archivo: %s", self._ruta)

    # ------------------------------------------------------------------
    #  5.1  Persistencia JSON
    # ------------------------------------------------------------------

    def _cargar(self) -> list[dict]:
        """Lee todos los pedidos del archivo JSON. Retorna lista vacía si no existe."""
        if not self._ruta.exists():
            return []
        try:
            with open(self._ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, list):
                logger.warning("El JSON de pedidos no es una lista. Reseteando.")
                return []
            return datos
        except json.JSONDecodeError as exc:
            logger.error("JSON de pedidos corrupto: %s — archivo reseteado.", exc)
            return []
        except OSError as exc:
            logger.error("No se pudo leer %s: %s", self._ruta, exc)
            return []

    def _guardar(self, pedidos: list[dict]) -> None:
        """Escribe la lista completa de pedidos al archivo JSON (sobrescribe)."""
        try:
            # Escritura atómica: escribir a .tmp y luego renombrar
            tmp = self._ruta.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(pedidos, f, ensure_ascii=False, indent=2)
            tmp.replace(self._ruta)
            logger.debug("Archivo de pedidos guardado (%d registros).", len(pedidos))
        except OSError as exc:
            logger.error("Error al guardar pedidos: %s", exc)
            raise PedidoError(f"No se pudo persistir el pedido: {exc}") from exc

    def _cargar_pedidos(self) -> list[Pedido]:
        """Carga y deserializa todos los pedidos."""
        return [Pedido.desde_dict(d) for d in self._cargar()]

    def _guardar_pedidos(self, pedidos: list[Pedido]) -> None:
        """Serializa y guarda todos los pedidos."""
        self._guardar([p.a_dict() for p in pedidos])

    # ------------------------------------------------------------------
    #  5.2  Crear pedido
    # ------------------------------------------------------------------

    def crear_pedido(
        self,
        cliente_nombre:   str,
        cliente_telefono: str,
        cliente_zona:     str,
        items:            list[dict],
        cliente_email:    str = "",
        notas:            str = "",
        usuario_id:       int | None = None,
    ) -> Pedido:
        """
        Crea, valida y persiste un nuevo pedido.

        Args:
            cliente_nombre:   Nombre completo del cliente.
            cliente_telefono: Número de WhatsApp/teléfono.
            cliente_zona:     Barrio o zona de entrega en La Paz.
            items:            Lista de dicts con 'producto_id' y 'cantidad'.
                              Ej: [{"producto_id": 1, "cantidad": 2}]
            cliente_email:    Correo opcional.
            notas:            Instrucciones adicionales opcionales.
            usuario_id:       ID del usuario autenticado (o None si es anónimo).

        Returns:
            El objeto Pedido creado y persistido.

        Raises:
            PedidoError: Si la validación falla o no se puede guardar.
        """
        # ---- Validar campos obligatorios ------------------------------------
        errores = _validar_datos_cliente(
            cliente_nombre, cliente_telefono, cliente_zona
        )
        if not items:
            errores.append("El pedido debe incluir al menos un producto.")

        if errores:
            raise PedidoError("Datos inválidos: " + " | ".join(errores))

        # ---- Construir ítems -----------------------------------------------
        items_construidos: list[ItemPedido] = []
        for entrada in items:
            item = _construir_item(entrada)
            items_construidos.append(item)

        # ---- Crear objeto Pedido -------------------------------------------
        pedido = Pedido(
            cliente_nombre=   cliente_nombre.strip(),
            cliente_telefono= cliente_telefono.strip(),
            cliente_zona=     cliente_zona.strip(),
            cliente_email=    cliente_email.strip().lower(),
            items=            items_construidos,
            notas=            notas.strip(),
            usuario_id=       usuario_id,
        )

        # ---- Persistir -------------------------------------------------------
        todos = self._cargar()
        todos.append(pedido.a_dict())
        self._guardar(todos)

        logger.info(
            "Pedido creado — número=%s  cliente=%s  total=Bs.%.2f  ítems=%d",
            pedido.numero, pedido.cliente_nombre,
            pedido.total_bs, len(pedido.items),
        )

        return pedido

    # ------------------------------------------------------------------
    #  5.3  Listar pedidos
    # ------------------------------------------------------------------

    def listar_pedidos(
        self,
        estado:     str | None = None,
        zona:       str | None = None,
        usuario_id: int | None = None,
        limite:     int | None = None,
        mas_recientes_primero: bool = True,
    ) -> list[Pedido]:
        """
        Retorna todos los pedidos, con filtros opcionales.

        Args:
            estado:     Filtrar por estado (ej: "pendiente").
            zona:       Filtrar por zona del cliente (búsqueda parcial).
            usuario_id: Filtrar por ID de usuario autenticado.
            limite:     Máximo de resultados a devolver.
            mas_recientes_primero: Orden cronológico inverso si True.

        Returns:
            Lista de objetos Pedido.
        """
        pedidos = self._cargar_pedidos()

        if estado:
            pedidos = [p for p in pedidos if p.estado == estado]

        if zona:
            zona_lower = zona.lower()
            pedidos = [
                p for p in pedidos
                if zona_lower in p.cliente_zona.lower()
            ]

        if usuario_id is not None:
            pedidos = [p for p in pedidos if p.usuario_id == usuario_id]

        pedidos.sort(
            key=lambda p: p.creado_en,
            reverse=mas_recientes_primero,
        )

        if limite:
            pedidos = pedidos[:limite]

        logger.debug(
            "listar_pedidos — filtros=(estado=%s, zona=%s, uid=%s)  resultados=%d",
            estado, zona, usuario_id, len(pedidos),
        )

        return pedidos

    # ------------------------------------------------------------------
    #  5.4  Buscar pedido por número o ID
    # ------------------------------------------------------------------

    def buscar_pedido(self, numero_o_id: str) -> Pedido | None:
        """
        Busca un pedido por su número (ej: "AVN-20240601-0001") o su UUID.
        Retorna el Pedido si lo encuentra, o None.
        """
        todos = self._cargar_pedidos()
        for pedido in todos:
            if pedido.numero == numero_o_id or pedido.id == numero_o_id:
                return pedido
        logger.debug("Pedido no encontrado: %s", numero_o_id)
        return None

    # ------------------------------------------------------------------
    #  5.5  Cambiar estado de un pedido
    # ------------------------------------------------------------------

    def cambiar_estado(
        self,
        numero_o_id: str,
        nuevo_estado: str,
        nota: str = "",
    ) -> Pedido:
        """
        Cambia el estado de un pedido existente y guarda el cambio.

        Args:
            numero_o_id: Número o UUID del pedido.
            nuevo_estado: Estado destino (debe ser una transición válida).
            nota: Comentario opcional que se agrega al historial.

        Returns:
            El Pedido actualizado.

        Raises:
            PedidoError: Si no se encuentra el pedido o la transición no es válida.
        """
        todos = self._cargar_pedidos()

        for i, pedido in enumerate(todos):
            if pedido.numero == numero_o_id or pedido.id == numero_o_id:
                pedido.cambiar_estado(nuevo_estado, nota)
                self._guardar_pedidos(todos)
                return pedido

        raise PedidoError(f"Pedido '{numero_o_id}' no encontrado.")

    # ------------------------------------------------------------------
    #  5.6  Confirmar pedido
    # ------------------------------------------------------------------

    def confirmar_pedido(self, numero_o_id: str, nota: str = "") -> Pedido:
        """Atajo: pasa el pedido de 'pendiente' a 'confirmado'."""
        return self.cambiar_estado(
            numero_o_id, "confirmado",
            nota or "Pedido confirmado por el equipo Avicor.",
        )

    # ------------------------------------------------------------------
    #  5.7  Marcar como en camino
    # ------------------------------------------------------------------

    def marcar_en_camino(self, numero_o_id: str, nota: str = "") -> Pedido:
        """Atajo: pasa el pedido de 'confirmado' a 'en_camino'."""
        return self.cambiar_estado(
            numero_o_id, "en_camino",
            nota or "El pedido salió hacia La Paz con cadena de frío.",
        )

    # ------------------------------------------------------------------
    #  5.8  Marcar como entregado
    # ------------------------------------------------------------------

    def marcar_entregado(self, numero_o_id: str, nota: str = "") -> Pedido:
        """Atajo: pasa el pedido de 'en_camino' a 'entregado'."""
        return self.cambiar_estado(
            numero_o_id, "entregado",
            nota or "Entregado correctamente al cliente.",
        )

    # ------------------------------------------------------------------
    #  5.9  Cancelar pedido
    # ------------------------------------------------------------------

    def cancelar_pedido(self, numero_o_id: str, motivo: str = "") -> Pedido:
        """Cancela un pedido activo."""
        return self.cambiar_estado(
            numero_o_id, "cancelado",
            motivo or "Pedido cancelado.",
        )

    # ------------------------------------------------------------------
    #  5.10  Estadísticas
    # ------------------------------------------------------------------

    def estadisticas(self) -> dict:
        """
        Calcula estadísticas básicas sobre todos los pedidos.

        Retorna un dict con:
            total_pedidos, por_estado, total_facturado_bs,
            promedio_pedido_bs, producto_mas_pedido
        """
        todos = self._cargar_pedidos()

        if not todos:
            return {
                "total_pedidos":      0,
                "por_estado":         {e: 0 for e in ESTADOS_VALIDOS},
                "total_facturado_bs": 0.0,
                "promedio_pedido_bs": 0.0,
                "producto_mas_pedido": None,
            }

        # Conteo por estado
        por_estado: dict[str, int] = {e: 0 for e in ESTADOS_VALIDOS}
        for p in todos:
            por_estado[p.estado] = por_estado.get(p.estado, 0) + 1

        # Total facturado (solo pedidos no cancelados)
        entregados = [p for p in todos if p.estado == "entregado"]
        total_facturado = sum(p.total_bs for p in entregados)
        promedio = total_facturado / len(entregados) if entregados else 0.0

        # Producto más pedido
        conteo_productos: dict[str, int] = {}
        for p in todos:
            for item in p.items:
                nombre = item.nombre_producto
                conteo_productos[nombre] = conteo_productos.get(nombre, 0) + item.cantidad

        producto_top = (
            max(conteo_productos, key=conteo_productos.get)
            if conteo_productos else None
        )

        return {
            "total_pedidos":       len(todos),
            "por_estado":          por_estado,
            "total_facturado_bs":  round(total_facturado, 2),
            "promedio_pedido_bs":  round(promedio, 2),
            "producto_mas_pedido": producto_top,
        }

    # ------------------------------------------------------------------
    #  5.11  Exportar pedidos a JSON limpio (para backup / reportes)
    # ------------------------------------------------------------------

    def exportar_json(self, ruta_destino: str | Path | None = None) -> str:
        """
        Exporta todos los pedidos a un JSON formateado.

        Args:
            ruta_destino: Ruta del archivo destino. Si es None, retorna el JSON
                          como string sin escribir archivo.

        Returns:
            El JSON serializado como string.
        """
        todos = self._cargar()
        json_str = json.dumps(todos, ensure_ascii=False, indent=2)

        if ruta_destino:
            with open(ruta_destino, "w", encoding="utf-8") as f:
                f.write(json_str)
            logger.info("Pedidos exportados a %s", ruta_destino)

        return json_str

    # ------------------------------------------------------------------
    #  5.12  Limpiar pedidos (solo para tests)
    # ------------------------------------------------------------------

    def _limpiar_todo(self) -> None:
        """⚠️ Borra TODOS los pedidos del archivo JSON. Solo para tests."""
        self._guardar([])
        logger.warning("Todos los pedidos han sido eliminados.")


# ==============================================================================
#  6. SIMULACIÓN DE COMPRA — Flujo completo demostrativo
# ==============================================================================

class SimuladorCompra:
    """
    Simula el flujo completo de una compra en Origen Avicor:
        Cliente elige productos
        → Pedido creado (pendiente)
        → Operador confirma (confirmado)
        → Sale de Coroico (en_camino)
        → Llega a La Paz (entregado)

    Se usa para demostración, tests y onboarding del equipo.
    """

    def __init__(self, gestor: GestorPedidos | None = None) -> None:
        self.gestor = gestor or GestorPedidos()
        self.pausa  = 0.6   # segundos entre cada paso (para demo visual)

    def ejecutar(
        self,
        cliente_nombre:   str = "María García",
        cliente_telefono: str = "+591 76543210",
        cliente_zona:     str = "Miraflores",
        items_demo:       list[dict] | None = None,
        pausas:           bool = True,
    ) -> Pedido:
        """
        Ejecuta la simulación completa de una compra.

        Args:
            cliente_nombre, cliente_telefono, cliente_zona: Datos del cliente demo.
            items_demo: Lista de ítems. Si es None usa items predeterminados.
            pausas: Si True, agrega una pequeña pausa entre pasos para demo visual.

        Returns:
            El Pedido final en estado 'entregado'.
        """
        items_demo = items_demo or [
            {"producto_id": 1, "cantidad": 1},   # Pollo entero
            {"producto_id": 4, "cantidad": 2},   # Muslos sazonados x2
        ]

        _sep()
        _print("🛒  SIMULACIÓN DE COMPRA — Origen Avicor")
        _sep()
        _print(f"  Cliente:   {cliente_nombre}")
        _print(f"  Teléfono:  {cliente_telefono}")
        _print(f"  Zona:      {cliente_zona}")
        _print(f"  Productos: {len(items_demo)} líneas")
        _sep()

        # ---- PASO 1: Crear pedido -------------------------------------------
        _print("\n[1/4] 📦  Creando pedido...")
        _pausa(pausas, self.pausa)

        pedido = self.gestor.crear_pedido(
            cliente_nombre=   cliente_nombre,
            cliente_telefono= cliente_telefono,
            cliente_zona=     cliente_zona,
            items=            items_demo,
            notas=            "Simulación de compra — demo Avicor",
        )

        _print(f"      ✅  Pedido {pedido.numero} creado.")
        _print(pedido.resumen())

        # ---- PASO 2: Confirmar ----------------------------------------------
        _print("\n[2/4] ✅  Confirmar pedido (operador Avicor)...")
        _pausa(pausas, self.pausa)

        pedido = self.gestor.confirmar_pedido(
            pedido.numero,
            nota="Pago verificado. Pedido en cola de despacho.",
        )
        _print(f"      Estado actual: {pedido.estado.upper()}")

        # ---- PASO 3: En camino ----------------------------------------------
        _print("\n[3/4] 🚚  El pedido sale de Coroico hacia La Paz...")
        _pausa(pausas, self.pausa)

        pedido = self.gestor.marcar_en_camino(
            pedido.numero,
            nota=f"Salió de Coroico. Cadena de frío activa. Destino: {cliente_zona}.",
        )
        _print(f"      Estado actual: {pedido.estado.upper()}")

        # ---- PASO 4: Entregado ----------------------------------------------
        _print("\n[4/4] 🏠  El pedido llega al cliente...")
        _pausa(pausas, self.pausa)

        pedido = self.gestor.marcar_entregado(
            pedido.numero,
            nota=f"Entregado a {cliente_nombre} en {cliente_zona}. Cliente conforme.",
        )
        _print(f"      Estado actual: {pedido.estado.upper()}")

        # ---- Resumen del historial ------------------------------------------
        _sep()
        _print("  HISTORIAL DE ESTADOS:")
        for evento in pedido.historial_estados:
            ts   = evento.get("timestamp", "")[:19]
            est  = evento.get("estado",    "?").upper()
            nota = evento.get("nota",      "")
            _print(f"    [{ts}]  {est:<12}  {nota}")
        _sep()
        _print(f"  🎉  Simulación completada exitosamente.")
        _print(f"  Pedido final: {pedido.numero}  •  Total: Bs. {pedido.total_bs:.2f}")
        _sep()

        return pedido


# ==============================================================================
#  7. FUNCIONES DE CONVENIENCIA (interfaz simplificada para app.py)
# ==============================================================================

# Instancia global del gestor
_gestor = GestorPedidos()


def crear_pedido(
    cliente_nombre:   str,
    cliente_telefono: str,
    cliente_zona:     str,
    items:            list[dict],
    cliente_email:    str = "",
    notas:            str = "",
    usuario_id:       int | None = None,
) -> Pedido:
    """
    Crea un pedido usando el gestor global.

    Ejemplo en app.py:
        from pedidos import crear_pedido
        pedido = crear_pedido(
            cliente_nombre="Juan Pérez",
            cliente_telefono="+591 77000000",
            cliente_zona="Sopocachi",
            items=[{"producto_id": 3, "cantidad": 1}]
        )
        return jsonify({"numero": pedido.numero, "total": pedido.total_bs})
    """
    return _gestor.crear_pedido(
        cliente_nombre=   cliente_nombre,
        cliente_telefono= cliente_telefono,
        cliente_zona=     cliente_zona,
        items=            items,
        cliente_email=    cliente_email,
        notas=            notas,
        usuario_id=       usuario_id,
    )


def listar_pedidos(
    estado:     str | None = None,
    zona:       str | None = None,
    usuario_id: int | None = None,
    limite:     int | None = None,
) -> list[Pedido]:
    """Lista pedidos con filtros opcionales usando el gestor global."""
    return _gestor.listar_pedidos(
        estado=estado,
        zona=zona,
        usuario_id=usuario_id,
        limite=limite,
    )


def buscar_pedido(numero_o_id: str) -> Pedido | None:
    """Busca un pedido por número o UUID."""
    return _gestor.buscar_pedido(numero_o_id)


def cambiar_estado_pedido(numero_o_id: str, nuevo_estado: str, nota: str = "") -> Pedido:
    """Cambia el estado de un pedido."""
    return _gestor.cambiar_estado(numero_o_id, nuevo_estado, nota)


def estadisticas_pedidos() -> dict:
    """Retorna estadísticas globales de pedidos."""
    return _gestor.estadisticas()


# ==============================================================================
#  8. FUNCIONES AUXILIARES PRIVADAS
# ==============================================================================

def _generar_id() -> str:
    """Genera un UUID v4 único para el pedido."""
    return str(uuid.uuid4())


def _generar_numero(timestamp_iso: str) -> str:
    """
    Genera un número de pedido legible.
    Formato: AVN-YYYYMMDD-NNNN
    donde NNNN es la parte final del UUID (para unicidad).
    """
    try:
        dt = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        dt = datetime.now()
    parte_uuid = uuid.uuid4().hex[:4].upper()
    return f"AVN-{dt.strftime('%Y%m%d')}-{parte_uuid}"


def _evento_estado(estado: str, nota: str) -> dict:
    """Crea una entrada para el historial de estados del pedido."""
    return {
        "estado":    estado,
        "nota":      nota,
        "timestamp": datetime.now().isoformat(),
    }


def _construir_item(entrada: dict) -> ItemPedido:
    """
    Construye un ItemPedido a partir de un dict con 'producto_id' y 'cantidad'.
    Consulta el CATALOGO para obtener nombre y precio.

    Raises:
        PedidoError si el producto no existe o los datos son inválidos.
    """
    producto_id = entrada.get("producto_id")
    cantidad    = entrada.get("cantidad", 1)

    if not isinstance(producto_id, int):
        raise PedidoError(
            f"'producto_id' debe ser un entero. Recibido: {producto_id!r}"
        )
    if not isinstance(cantidad, int) or cantidad < 1:
        raise PedidoError(
            f"'cantidad' debe ser un entero positivo. Recibido: {cantidad!r}"
        )
    if producto_id not in CATALOGO:
        raise PedidoError(
            f"Producto con id={producto_id} no existe en el catálogo. "
            f"IDs válidos: {sorted(CATALOGO.keys())}"
        )

    prod = CATALOGO[producto_id]
    return ItemPedido(
        producto_id=     producto_id,
        nombre_producto= prod["nombre"],
        precio_unitario= prod["precio"],
        cantidad=        cantidad,
    )


def _validar_datos_cliente(
    nombre: str, telefono: str, zona: str
) -> list[str]:
    """
    Valida los datos básicos del cliente.
    Retorna lista de strings con los errores encontrados (vacía si todo ok).
    """
    errores: list[str] = []

    if not nombre or len(nombre.strip()) < 2:
        errores.append("El nombre del cliente debe tener al menos 2 caracteres.")

    if not telefono or len(telefono.strip()) < 7:
        errores.append("El teléfono debe tener al menos 7 dígitos.")

    if re.search(r"[<>\"'&]", nombre + zona):
        errores.append("Los datos contienen caracteres no permitidos.")

    if not zona or len(zona.strip()) < 2:
        errores.append("La zona de entrega es obligatoria.")

    return errores


def _sep() -> None:
    """Imprime un separador visual en la demo."""
    print("─" * 56)


def _print(msg: str) -> None:
    """Imprime un mensaje en la demo."""
    print(msg)


def _pausa(activa: bool, segundos: float) -> None:
    """Pausa la ejecución si `activa` es True."""
    if activa:
        time.sleep(segundos)


# ==============================================================================
#  9. BLOQUE DE EJECUCIÓN DIRECTA — Demo completa
#  Ejecutar:  python pedidos.py
# ==============================================================================

if __name__ == "__main__":
    import sys

    print("\n" + "═" * 56)
    print("  ORIGEN AVICOR — Demo del módulo pedidos.py")
    print("═" * 56)

    gestor    = GestorPedidos()
    simulador = SimuladorCompra(gestor)

    # ------------------------------------------------------------------
    # A) Catálogo disponible
    # ------------------------------------------------------------------
    print("\n📋  CATÁLOGO DE PRODUCTOS:\n")
    for pid, prod in CATALOGO.items():
        print(f"  [{pid:2d}]  {prod['nombre']:<40} Bs. {prod['precio']:.2f} / {prod['unidad']}")

    # ------------------------------------------------------------------
    # B) Crear pedidos de prueba directamente
    # ------------------------------------------------------------------
    print("\n\n📦  CREANDO PEDIDOS DE PRUEBA...\n")

    pedidos_demo = [
        {
            "cliente_nombre":   "Carlos Tarqui",
            "cliente_telefono": "+591 71234567",
            "cliente_zona":     "Sopocachi",
            "items": [
                {"producto_id": 6, "cantidad": 1},   # Pollo orgánico
                {"producto_id": 2, "cantidad": 2},   # Pechuga x2
            ],
        },
        {
            "cliente_nombre":   "Ana Solís",
            "cliente_telefono": "+591 76543210",
            "cliente_zona":     "Calacoto",
            "items": [
                {"producto_id": 3, "cantidad": 1},   # Pack Familiar
            ],
            "notas": "Entregar entre 8am y 10am por favor.",
        },
        {
            "cliente_nombre":   "Roberto Mamani",
            "cliente_telefono": "+591 79876543",
            "cliente_zona":     "Miraflores",
            "items": [
                {"producto_id": 9,  "cantidad": 1},  # Pack Parrillero
                {"producto_id": 7,  "cantidad": 3},  # Menudencias x3
                {"producto_id": 12, "cantidad": 2},  # Pollo pequeño x2
            ],
        },
    ]

    creados: list[Pedido] = []
    for datos in pedidos_demo:
        try:
            p = gestor.crear_pedido(**datos)
            creados.append(p)
            print(f"  ✅  {p.numero}  |  {p.cliente_nombre:<20}  |  Bs. {p.total_bs:.2f}")
        except PedidoError as e:
            print(f"  ❌  Error al crear pedido: {e}")

    # ------------------------------------------------------------------
    # C) Listar todos los pedidos
    # ------------------------------------------------------------------
    print("\n\n📋  TODOS LOS PEDIDOS (más recientes primero):\n")
    todos = gestor.listar_pedidos()
    if todos:
        print(f"  {'Número':<22}  {'Cliente':<20}  {'Zona':<14}  {'Total':>8}  Estado")
        print(f"  {'─'*22}  {'─'*20}  {'─'*14}  {'─'*8}  {'─'*12}")
        for p in todos:
            print(
                f"  {p.numero:<22}  {p.cliente_nombre:<20}  "
                f"{p.cliente_zona:<14}  Bs.{p.total_bs:>6.2f}  {p.estado}"
            )
    else:
        print("  (sin pedidos)")

    # ------------------------------------------------------------------
    # D) Filtrar por estado
    # ------------------------------------------------------------------
    pendientes = gestor.listar_pedidos(estado="pendiente")
    print(f"\n  Pedidos pendientes: {len(pendientes)}")

    # ------------------------------------------------------------------
    # E) Buscar un pedido específico
    # ------------------------------------------------------------------
    if creados:
        numero_buscar = creados[0].numero
        print(f"\n\n🔍  BUSCAR PEDIDO: {numero_buscar}\n")
        encontrado = gestor.buscar_pedido(numero_buscar)
        if encontrado:
            print(encontrado.resumen())

    # ------------------------------------------------------------------
    # F) Avanzar estados manualmente
    # ------------------------------------------------------------------
    if len(creados) >= 2:
        print("\n\n⚙️   AVANZAR ESTADOS DEL PEDIDO #2...\n")
        try:
            p2 = creados[1]
            gestor.confirmar_pedido(p2.numero)
            print(f"  {p2.numero}  →  confirmado")
            gestor.marcar_en_camino(p2.numero)
            print(f"  {p2.numero}  →  en_camino")
            gestor.marcar_entregado(p2.numero)
            print(f"  {p2.numero}  →  entregado  ✅")
        except PedidoError as e:
            print(f"  ❌  {e}")

    # ------------------------------------------------------------------
    # G) Probar transición inválida
    # ------------------------------------------------------------------
    if creados:
        print("\n\n⚠️   PROBAR TRANSICIÓN INVÁLIDA...\n")
        try:
            gestor.cambiar_estado(creados[0].numero, "entregado")
        except PedidoError as e:
            print(f"  ✅  Error esperado capturado: {e}")

    # ------------------------------------------------------------------
    # H) Estadísticas
    # ------------------------------------------------------------------
    print("\n\n📊  ESTADÍSTICAS:\n")
    stats = gestor.estadisticas()
    print(f"  Total pedidos:       {stats['total_pedidos']}")
    print(f"  Total facturado:     Bs. {stats['total_facturado_bs']:.2f}")
    print(f"  Promedio por pedido: Bs. {stats['promedio_pedido_bs']:.2f}")
    print(f"  Producto más pedido: {stats['producto_mas_pedido'] or '—'}")
    print(f"  Por estado:")
    for estado, cant in stats["por_estado"].items():
        if cant:
            print(f"    {estado:<14} {cant}")

    # ------------------------------------------------------------------
    # I) Simulación de compra completa
    # ------------------------------------------------------------------
    print("\n\n")
    simulador.ejecutar(
        cliente_nombre=   "Patricia Ríos",
        cliente_telefono= "+591 77001122",
        cliente_zona=     "San Miguel",
        items_demo=[
            {"producto_id": 6,  "cantidad": 1},   # Pollo orgánico
            {"producto_id": 11, "cantidad": 1},   # Pechuga entera 1kg
        ],
        pausas=True,
    )

    # ------------------------------------------------------------------
    # J) Exportar JSON
    # ------------------------------------------------------------------
    print("\n\n💾  EXPORTAR JSON...\n")
    json_exportado = gestor.exportar_json()
    total_exportados = len(json.loads(json_exportado))
    print(f"  ✅  {total_exportados} pedidos exportados correctamente.")
    print(f"  Archivo: {PEDIDOS_JSON.resolve()}")

    print("\n" + "═" * 56)
    print("  Demo completada.")
    print("═" * 56 + "\n")

    sys.exit(0)