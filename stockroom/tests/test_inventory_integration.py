
from django.db.models import Exists, OuterRef, F

from stockroom.models import (
    Article,
    Tool,
    Loan,
    QuantityStock,
    QuantityIssue,
    MaterialRequest,
    MaterialRequestPiece,
)

print("\n========== DIAGNOSTICO STOCKROOMER ==========\n")

print("RESUMEN DE REGISTROS")
print("Articulos:", Article.objects.count())
print("Articulos por cantidad:", Article.objects.filter(tracking_mode="quantity").count())
print("Articulos individuales:", Article.objects.filter(tracking_mode="individual").count())
print("Herramientas individuales:", Tool.objects.count())
print("Solicitudes:", MaterialRequest.objects.count())
print("Entregas registradas:", QuantityIssue.objects.count())

print("\nREVISION DE EXISTENCIAS")

sin_stock = Article.objects.filter(
    tracking_mode="quantity",
    quantity_stock__isnull=True,
)

print("Articulos por cantidad sin registro de existencias:", sin_stock.count())

for articulo in sin_stock[:10]:
    print("  REVISAR:", articulo.article_code)

stock_incorrecto = QuantityStock.objects.exclude(
    article__tracking_mode="quantity"
)

print("Existencias asociadas a control incorrecto:", stock_incorrecto.count())

print("\nREVISION DE ENTREGAS")

entregas_invalidas = QuantityIssue.objects.filter(
    returned_quantity__gt=F("quantity")
)

print("Entregas con devoluciones mayores a lo entregado:", entregas_invalidas.count())

prestamos_abiertos = Loan.objects.filter(
    tool_id=OuterRef("pk"),
    returned_at__isnull=True,
)

entregas_abiertas = QuantityIssue.objects.filter(
    tool_id=OuterRef("pk"),
    requires_return=True,
    returned_quantity__lt=F("quantity"),
)

herramientas = Tool.objects.annotate(
    tiene_loan=Exists(prestamos_abiertos),
    tiene_entrega=Exists(entregas_abiertas),
)

inconsistencias = []

for herramienta in herramientas:
    prestada = (
        herramienta.tiene_loan
        or herramienta.tiene_entrega
    )

    if prestada and herramienta.inventory_status == "available":
        inconsistencias.append(
            (herramienta.tool_code, "Disponible pero tiene entrega abierta")
        )

    elif (
        not prestada
        and herramienta.inventory_status == "loaned"
    ):
        inconsistencias.append(
            (herramienta.tool_code, "Prestada pero sin entrega abierta")
        )

print("Posibles inconsistencias de estado:", len(inconsistencias))

for codigo, detalle in inconsistencias[:20]:
    print("  REVISAR:", codigo, "-", detalle)

print("\nREVISION DE SOLICITUDES")

piezas_incorrectas = MaterialRequestPiece.objects.exclude(
    tool__article_id=F("line__article_id")
)

print(
    "Piezas seleccionadas de articulo diferente:",
    piezas_incorrectas.count()
)

print("\n========== DIAGNOSTICO FINALIZADO ==========")
print("Este diagnostico no modifico la base de datos.")

