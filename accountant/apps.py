from django.apps import AppConfig


class AccountantConfig(AppConfig):
    name = "accountant"
    verbose_name = "AA Accountant"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from accountant import checks  # noqa: F401
