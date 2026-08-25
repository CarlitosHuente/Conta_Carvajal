from django.core.management.base import BaseCommand

from invergesal.services.ais_stream import recolectar_ais


class Command(BaseCommand):
    help = 'Escucha AISStream unos segundos y actualiza escalas a San Antonio / Valparaíso.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--segundos',
            type=int,
            default=None,
            help='Duración de la escucha (20-180). Por defecto INVERGESAL_AIS_LISTEN_SECONDS.',
        )

    def handle(self, *args, **options):
        n, mensaje = recolectar_ais(options.get('segundos'))
        if n:
            self.stdout.write(self.style.SUCCESS(mensaje))
        else:
            self.stdout.write(self.style.WARNING(mensaje))
