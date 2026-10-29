from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.models import UUIDModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.SYSTEM_ADMIN)
        return self._create(email, password, **extra)


class User(UUIDModel, AbstractUser):
    """
    Email-based authentication. `role` is the primary role used for UI routing;
    actual access is checked through membership / profile tables.
    """

    class Role(models.TextChoices):
        SYSTEM_ADMIN = "system_admin", "System Admin"
        COMPANY_STAFF = "company_staff", "Courier Company Staff"
        CLIENT_STAFF = "client_staff", "Client (Shop/Warehouse) Staff"
        COURIER = "courier", "Courier"

    username = None
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT_STAFF)
    telegram_chat_id = models.CharField(max_length=50, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []
    objects = UserManager()

    def __str__(self) -> str:
        return self.email
