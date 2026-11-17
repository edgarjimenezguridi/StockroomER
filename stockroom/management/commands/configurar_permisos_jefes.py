
"""Configura permisos mínimos de consulta para el grupo Jefes."""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


PERMISOS_LECTURA = (
    "view_materialrequest",
    "view_employee",
    "view_quantityissue",
    "view_article",
    "view_quantitystock",
    "view_tool",
)


class Command(BaseCommand):
    help = (
        "Revisa o configura los permisos de consulta "
        "del grupo Jefes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica los permisos. Sin esta opción solo revisa.",
        )

    def handle(self, *args, **options):
        permisos = list(
            Permission.objects.filter(
                content_type__app_label="stockroom",
                codename__in=PERMISOS_LECTURA,
            ).select_related("content_type")
        )

        encontrados = {p.codename for p in permisos}
        faltantes = set(PERMISOS_LECTURA) - encontrados

        if faltantes:
            raise CommandError(
                "No se encontraron estos permisos: "
                + ", ".join(sorted(faltantes))
            )

        grupo = Group.objects.filter(name="Jefes").first()

        actuales = set()
        if grupo:
            actuales = set(
                grupo.permissions.values_list(
                    "codename", flat=True
                )
            )

        nuevos = set(PERMISOS_LECTURA) - actuales

        self.stdout.write("Grupo: Jefes")
        self.stdout.write(
            f"Permisos de consulta pendientes: {len(nuevos)}"
        )

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "Modo revisión: no se modificó la base de datos."
                )
            )
            return

        with transaction.atomic():
            grupo, _ = Group.objects.get_or_create(
                name="Jefes"
            )
            grupo.permissions.add(*permisos)

        self.stdout.write(
            self.style.SUCCESS(
                "Permisos de consulta configurados correctamente."
            )
        )
        self.stdout.write(
            "No se modificaron usuarios ni permisos de escritura."
        )
