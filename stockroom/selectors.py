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
    piezas_con_pendiente = QuantityIssue.objects.filter(
        tool__isnull=False,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
    ).values("tool_id")

    prestamos_sin_importar = Loan.objects.filter(
        returned_at__isnull=True,
        unified_issue__isnull=True,
    ).values("tool_id")

    return (
        Tool.objects.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
        )
        .exclude(pk__in=piezas_con_pendiente)
        .exclude(pk__in=prestamos_sin_importar)
        .select_related("article")
    )

def catalogo_articulos(search=""):
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