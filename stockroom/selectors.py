
from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from .models import Article, Loan, QuantityIssue, Tool


def piezas_individuales_disponibles():
    """
    Devuelve exclusivamente herramientas individuales que
    pueden seleccionarse para una nueva entrega.

    Se excluyen:
    - Piezas inactivas.
    - Piezas con estado diferente de disponible.
    - Articulos inactivos.
    - Entregas unificadas pendientes.
    - Todos los prestamos antiguos abiertos, incluidos
      los vinculados a una entrega unificada.
    """

    piezas_con_pendiente = (
        QuantityIssue.objects.filter(
            tool__isnull=False,
            requires_return=True,
            returned_quantity__lt=F("quantity"),
        )
        .values("tool_id")
    )

    # No ignorar prestamos legacy que ya fueron importados.
    # Si Loan.returned_at es NULL, la pieza sigue bloqueada.
    prestamos_abiertos = (
        Loan.objects.filter(
            returned_at__isnull=True,
        )
        .values("tool_id")
    )

    return (
        Tool.objects.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
        )
        .exclude(pk__in=piezas_con_pendiente)
        .exclude(pk__in=prestamos_abiertos)
        .select_related("article")
    )


def catalogo_articulos(search=""):
    """
    Consulta el catalogo de articulos activos.

    Para articulos individuales, la disponibilidad se
    calcula utilizando el selector protegido.
    """

    piezas_por_articulo = (
        piezas_individuales_disponibles()
        .filter(article_id=OuterRef("pk"))
        .order_by()
        .values("article_id")
        .annotate(total=Count("pk"))
        .values("total")
    )

    articles = (
        Article.objects.filter(is_active=True)
        .select_related("specification__tool_type__category")
        .annotate(
            available_quantity=Case(
                When(
                    tracking_mode=Article.TrackingMode.QUANTITY,
                    then=Coalesce(
                        F("quantity_stock__available_quantity"),
                        Value(0),
                    ),
                ),
                When(
                    tracking_mode=Article.TrackingMode.INDIVIDUAL,
                    then=Coalesce(
                        Subquery(
                            piezas_por_articulo,
                            output_field=IntegerField(),
                        ),
                        Value(0),
                    ),
                ),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("name", "article_code")
    )

    search = search.strip()

    if search:
        articles = articles.filter(
            Q(article_code__icontains=search)
            | Q(name__icontains=search)
            | Q(brand__icontains=search)
            | Q(specification__name__icontains=search)
            | Q(specification__tool_type__name__icontains=search)
            | Q(
                specification__tool_type__category__name__icontains=search
            )
        )

    return articles
