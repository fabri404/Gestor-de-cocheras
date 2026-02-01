from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.user.username
    
    
class EmpleadoAsignacion(models.Model):
    dueno = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="empleados_asignados",
    )
    empleado = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dueno_asignado",
    )
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(dueno=models.F("empleado")),
                name="ck_empleado_no_es_su_propio_dueno",
            )
        ]

    def __str__(self):
        return f"{self.empleado.username} -> {self.dueno.username}"
