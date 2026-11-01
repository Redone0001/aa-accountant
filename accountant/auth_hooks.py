from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from accountant import urls


class AccountantMenu(MenuItemHook):
    def __init__(self):
        super().__init__(
            "Accountant", "fas fa-chart-line fa-fw", "accountant:index", navactive=["accountant:"]
        )

    def render(self, request):
        if request.user.has_perm("accountant.view_dashboard"):
            return super().render(request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return AccountantMenu()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "accountant", r"^accountant/")
