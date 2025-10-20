# app/report_generator.py
import os
from io import BytesIO
import matplotlib
matplotlib.use("Agg")  # backend sin pantalla
import matplotlib.pyplot as plt
from typing import List, Dict, Any
from PIL import Image
from docxtpl import InlineImage
from docx.shared import Mm

# Import coherente dentro del paquete 'app'
from .config import (
    OUTPUT_DIR, CHART_WIDTH_MM, COLOR_CUMPLIMIENTO,
    COLOR_PENDIENTE, CHART_BG, IMAGE_MAX_WIDTH
)


def _resize_image_keep_ratio(data: bytes, max_w: int) -> bytes:
    """
    Redimensiona manteniendo proporción y devuelve bytes en formato
    PNG (si hay transparencia) o JPEG (si no la hay).
    """
    im = Image.open(BytesIO(data))
    # Redimensionar si es más ancha que max_w
    if im.width > max_w:
        ratio = max_w / float(im.width)
        new_size = (max_w, max(1, int(im.height * ratio)))
        im = im.resize(new_size, Image.LANCZOS)

    has_alpha = ("A" in im.getbands()) or (
        im.mode == "P" and "transparency" in im.info
    )

    out = BytesIO()
    if has_alpha:
        # Mantener transparencia -> PNG
        if im.mode not in ("RGBA", "LA"):
            im = im.convert("RGBA")
        im.save(out, format="PNG", optimize=True)
    else:
        # Sin transparencia -> JPEG
        if im.mode != "RGB":
            im = im.convert("RGB")
        im.save(out, format="JPEG", quality=90, optimize=True)

    return out.getvalue()


def build_context(doc, row: Dict[str, Any], images: List[bytes]) -> Dict[str, Any]:
    """
    Prepara el contexto para docxtpl. Convierte cada imagen en InlineImage.
    'row' debe venir preferentemente ya combinado (Proyectos + Informes).
    Se mantienen las claves antiguas para compatibilidad con plantillas previas.
    """
    imgs_tpl: List[InlineImage] = []
    for b in images:
        b = _resize_image_keep_ratio(b, IMAGE_MAX_WIDTH)
        imgs_tpl.append(InlineImage(doc, BytesIO(b)))  # tamaño ya viene escalado

    context: Dict[str, Any] = {
        # ---- Datos de Proyecto ----
        "nombre_proyecto": row.get("nombre_proyecto", ""),
        "promotor_representante": row.get("promotor_representante", ""),
        "licencia_ambiental": row.get("licencia_ambiental", ""),
        "sector_productivo": row.get("sector_productivo", ""),
        "ubicacion_politica": row.get("ubicacion_politica", ""),
        "area": row.get("area", ""),

        # ---- Metadatos del Informe ----
        "id_informe": row.get("id_informe", ""),
        "fecha": row.get("fecha", ""),
        "responsable": row.get("responsable", ""),

        # ---- Cuerpo Técnico de la Inspección ----
        "sitio_inspeccion": row.get("sitio_inspeccion", ""),
        "objetivo_visita": row.get("objetivo_visita", ""),
        "metodologia": row.get("metodologia", ""),
        "descripcion": row.get("descripcion", ""),
        "hallazgos": row.get("hallazgos", ""),
        "conformidades": row.get("conformidades", ""),
        "no_conformidades": row.get("no_conformidades", ""),
        "acciones_inmediatas": row.get("acciones_inmediatas", ""),
        "conclusiones": row.get("conclusiones", ""),
        "recomendaciones": row.get("recomendaciones", ""),
        "nivel_cumplimiento": row.get("nivel_cumplimiento", ""),

        # ---- Compatibilidad con plantillas anteriores ----
        "proyecto": row.get("proyecto", ""),   # antes se usaba como nombre del proyecto
        "cliente": row.get("cliente", ""),

        # ---- Imágenes ----
        "imagenes": imgs_tpl,
    }

    # === Inyección del gráfico de cumplimiento (sin cambiar estructura) ===
    def _to_float_pct(val) -> float:
        if val is None:
            return 0.0
        s = str(val).strip().replace("%", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0

    porcentaje = _to_float_pct(row.get("nivel_cumplimiento", 0))

    # Generar PNG (usa id_informe si existe para nombrar el archivo)
    ruta_png = generar_grafico_cumplimiento(
        porcentaje,
        nombre_base=f"cumplimiento_{row.get('id_informe', 'tmp')}"
    )

    # Insertar como InlineImage con ancho fijo desde config
    context["grafico_cumplimiento"] = InlineImage(
        doc,
        ruta_png,
        width=Mm(CHART_WIDTH_MM)
    )

    # (Opcional) exponer número limpio para mostrar "XX%"
    context["porcentaje_cumplimiento"] = f"{porcentaje:.0f}"

    return context


def generar_grafico_cumplimiento(porcentaje: float, nombre_base: str = "cumplimiento") -> str:
    """
    Genera un gráfico de pastel (cumplimiento vs pendiente) y devuelve la ruta PNG.
    - porcentaje: 0..100
    - nombre_base: prefijo del archivo
    """
    pct = max(0, min(100, float(porcentaje)))  # clamp
    pendientes = 100 - pct

    fig, ax = plt.subplots(figsize=(3.2, 3.2), dpi=150)  # tamaño base; luego se escala en DOCX
    fig.patch.set_facecolor(CHART_BG)

    # Datos y colores (branding)
    valores = [pct, pendientes]
    colores = [COLOR_CUMPLIMIENTO, COLOR_PENDIENTE]

    # Pastel tipo donut, porcentaje centrado solo en el segmento de cumplimiento
    wedges, texts, autotexts = ax.pie(
        valores,
        colors=colores,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.65, edgecolor=CHART_BG),
        autopct=lambda v: f"{pct:.0f}%" if abs(v - pct) < 1e-6 else "",
        pctdistance=0.0,  # texto al centro
    )

    # Círculo central (donut look)
    centre_circle = plt.Circle((0, 0), 0.52, fc=CHART_BG)
    fig.gca().add_artist(centre_circle)

    # Etiqueta central de seguridad
    ax.text(
        0, 0, f"{pct:.0f}%",
        va="center", ha="center",
        fontsize=16, color=COLOR_CUMPLIMIENTO, fontweight="bold"
    )

    ax.axis("equal")
    plt.tight_layout(pad=0.5)

    # Guardar PNG en OUTPUT_DIR
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(OUTPUT_DIR, f"{nombre_base}_{int(pct)}.png")
    fig.savefig(file_path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return file_path
