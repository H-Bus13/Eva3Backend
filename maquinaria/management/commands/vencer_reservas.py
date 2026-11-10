from django.core.management.base import BaseCommand
from maquinaria.reservas import vencer_reservas


class Command(BaseCommand):
    help = "Libera reservas de solicitudes aprobadas cuyo plazo de entrega venció."

    def handle(self, *args, **options):
        cantidad = vencer_reservas()
        self.stdout.write(self.style.SUCCESS(f"Reservas vencidas: {cantidad}."))
