
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.services import register_quantity_issue


class QuantityIssueInitialStateTests(TestCase):
    """
    Verifica que las entregas nuevas no puedan
    comenzar con cantidades ya devueltas.
    """

    def test_rechaza_entrega_nueva_con_devoluciones_previas(self):
        issue = SimpleNamespace(
            pk=None,
            _state=SimpleNamespace(adding=True),
            tool_id=None,
            returned_quantity=1,
        )

        with patch(
            "stockroom.services.Article.objects.get"
        ) as get_article:

            with self.assertRaisesMessage(
                ValidationError,
                "Una entrega nueva no puede tener "
                "piezas ya devueltas.",
            ):
                register_quantity_issue(issue)

            # El servicio debe rechazar la operación
            # antes de consultar artículos o modificar stock.
            get_article.assert_not_called()
