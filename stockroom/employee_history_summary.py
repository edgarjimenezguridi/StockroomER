
"""Cálculos de indicadores del expediente del trabajador.

No modifica inventario ni guarda registros.
"""


def calcular_resumen_devoluciones(
    *,
    total_devueltas,
    total_danadas,
    total_danos_resueltos,
):
    devueltas = int(total_devueltas or 0)
    danadas = int(total_danadas or 0)
    resueltas = int(total_danos_resueltos or 0)

    if min(devueltas, danadas, resueltas) < 0:
        raise ValueError("Las cantidades no pueden ser negativas.")

    if danadas > devueltas:
        raise ValueError(
            "Las devoluciones dañadas no pueden superar "
            "las devoluciones totales."
        )

    if resueltas > danadas:
        raise ValueError(
            "Los daños resueltos no pueden superar "
            "las piezas devueltas dañadas."
        )

    return {
        "total_devueltas": devueltas,
        "total_buen_estado": devueltas - danadas,
        "total_danadas": danadas,
        "total_danos_resueltos": resueltas,
        "total_danos_sin_resolver": danadas - resueltas,
    }
