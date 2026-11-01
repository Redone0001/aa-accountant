from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured

from accountant.conf import retention_months


@register()
def check_retention(app_configs, **kwargs):
    try:
        retention_months()
    except ImproperlyConfigured as error:
        return [Error(str(error), id="accountant.E001")]
    return []
