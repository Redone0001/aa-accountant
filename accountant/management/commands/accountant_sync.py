from django.core.management.base import BaseCommand, CommandError

from accountant.models import Corporation
from accountant.services.importer import prune_history, sync_corporation


class Command(BaseCommand):
    help = "Synchronize enabled corporation wallets and apply history retention."

    def add_arguments(self, parser):
        parser.add_argument("--corporation-id", type=int, help="EVE corporation ID (optional)")
        parser.add_argument("--prune-only", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(f"Pruned {prune_history()} old entries.")
        if options["prune_only"]:
            return
        corporations = Corporation.objects.filter(enabled=True)
        if options["corporation_id"]:
            corporations = corporations.filter(corporation_id=options["corporation_id"])
            if not corporations.exists():
                raise CommandError("No enabled corporation with this ID.")
        failed = False
        for corporation in corporations:
            try:
                count = sync_corporation(corporation.pk)
            except Exception:
                failed = True
                self.stderr.write(f"{corporation.name}: failed. See Wallet sources for status.")
            else:
                self.stdout.write(
                    f"{corporation.name}: processed {count} entries (including repeats)."
                )
        if failed:
            raise CommandError(
                "Some corporation imports failed; other corporations were processed."
            )
