from django.core.management.base import BaseCommand, CommandError
from maquinaria.models import Empresa
from maquinaria.servicios_bloqueos import revisar_atrasos


class Command(BaseCommand):
    help = "Actualiza bloqueos por atrasos sin aplicar cobros ni multas."

    def add_arguments(self, parser):
        parser.add_argument("--empresa", type=int, help="Revisar únicamente este ID de empresa")

    def handle(self, *args, **options):
        pk = options["empresa"]
        if pk is not None and not Empresa.objects.filter(pk=pk).exists():
            raise CommandError("La empresa indicada no existe.")
        revisadas, cambios = revisar_atrasos(pk)
        self.stdout.write(self.style.SUCCESS(f"Empresas revisadas: {revisadas}. Cambios de bloqueo automático: {cambios}."))
