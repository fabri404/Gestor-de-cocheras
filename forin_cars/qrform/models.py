import uuid
from django.db import models
from django.utils import timezone


class QRLink(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Control de validez
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Control de usos (opcional)
    max_uses = models.PositiveIntegerField(default=1)
    uses_count = models.PositiveIntegerField(default=0)

    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def can_be_used(self) -> bool:
        if not self.is_active:
            return False
        if self.is_expired():
            return False
        if self.uses_count >= self.max_uses:
            return False
        return True

    def __str__(self):
        return f"QRLink({self.token})"


class Submission(models.Model):
    qr_link = models.ForeignKey(QRLink, on_delete=models.PROTECT, related_name="submissions")

    # Campos ejemplo (ajustalos a tu dominio)
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Submission({self.full_name} -> {self.qr_link.token})"
