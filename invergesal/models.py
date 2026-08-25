from django.db import models


class EscalaNave(models.Model):
    PUERTO_CHOICES = (
        ('SAN ANTONIO', 'San Antonio'),
        ('VALPARAISO', 'Valparaíso'),
    )

    mmsi = models.CharField(max_length=16, unique=True, db_index=True)
    nombre = models.CharField(max_length=120, blank=True)
    tipo_ais = models.PositiveSmallIntegerField(null=True, blank=True)
    tipo_texto = models.CharField(max_length=40, blank=True)
    puerto_previsto = models.CharField(max_length=20, choices=PUERTO_CHOICES, db_index=True)
    destino_ais = models.CharField(max_length=80, blank=True)
    eta = models.DateTimeField(null=True, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=5, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=5, null=True, blank=True)
    rumbo = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    nudos = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    en_zona_puerto = models.BooleanField(default=False)
    visto_en = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = 'Escala de nave'
        verbose_name_plural = 'Escalas de naves'
        ordering = ['eta', 'nombre']

    def __str__(self):
        return f'{self.nombre or self.mmsi} → {self.puerto_previsto}'
