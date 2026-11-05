import django.db.models.deletion
from django.db import migrations, models


def copy_existing_loans(apps, schema_editor):
    Loan = apps.get_model("stockroom", "Loan")
    QuantityIssue = apps.get_model("stockroom", "QuantityIssue")
    database = schema_editor.connection.alias

    for loan in Loan.objects.using(database).order_by("pk").iterator():
        was_returned = loan.returned_at is not None

        notes = f"Importado del préstamo #{loan.pk}."

        if was_returned:
            notes += (
                "\nFecha de devolución original: "
                f"{loan.returned_at.isoformat()}"
                "\nCondición al regresar: no registrada "
                "en el sistema anterior."
            )

        QuantityIssue.objects.using(database).get_or_create(
            legacy_loan_id=loan.pk,
            defaults={
                "stock_id": None,
                "tool_id": loan.tool_id,
                "employee_id": loan.employee_id,
                "quantity": 1,
                "returned_quantity": 1 if was_returned else 0,
                "issued_at": loan.borrowed_at,
                "requires_return": True,
                "notes": notes,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("stockroom", "0018_tool_inventory_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="quantityissue",
            name="legacy_loan",
            field=models.OneToOneField(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="unified_issue",
                to="stockroom.loan",
                verbose_name="Préstamo de origen",
            ),
        ),
        migrations.RunPython(copy_existing_loans),
    ]