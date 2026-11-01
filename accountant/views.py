import csv
from datetime import datetime, time, timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from esi.decorators import token_required
from esi.models import Token

from accountant.conf import retention_cutoff
from accountant.forms import ExportForm, ReportForm
from accountant.models import Corporation, Dashboard, JournalEntry, WalletDivision
from accountant.services.esi import SCOPES, EsiError
from accountant.services.importer import authorize_corporation
from accountant.services.report import build_report, is_internal_transfer
from accountant.tasks import sync_wallets


@login_required
@permission_required("accountant.view_dashboard", raise_exception=True)
def index(request):
    return render(
        request,
        "accountant/index.html",
        {
            "dashboards": Dashboard.visible_to(request.user).prefetch_related(
                "divisions__corporation"
            ),
        },
    )


@login_required
@permission_required("accountant.view_dashboard", raise_exception=True)
def dashboard(request, pk):
    board = get_object_or_404(Dashboard.visible_to(request.user), pk=pk)
    data = {"year": now().year, "unit": board.default_unit}
    data.update(request.GET.dict())
    form = ReportForm(data, dashboard=board)
    report = None
    year, unit = now().year, board.default_unit
    if form.is_valid():
        year, unit = form.cleaned_data["year"], form.cleaned_data["unit"]
        report = build_report(board, year)
    return render(
        request,
        "accountant/dashboard.html",
        {
            "dashboard": board,
            "form": form,
            "report": report,
            "year": year,
            "unit": unit,
        },
    )


def export_divisions(user):
    if user.has_perm("accountant.manage_sources"):
        return WalletDivision.objects.select_related("corporation").all()
    return (
        WalletDivision.objects.filter(dashboards__in=Dashboard.visible_to(user))
        .select_related("corporation")
        .distinct()
    )


class CsvBuffer:
    def write(self, value):
        return value


def safe_csv_text(value):
    """Keep reasons/descriptions from becoming formulas when opened in a spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


@login_required
@permission_required("accountant.export_journal", raise_exception=True)
def export(request):
    form = ExportForm(request.GET or None, divisions=export_divisions(request.user))
    if form.is_bound and form.is_valid():
        division = form.cleaned_data["division"]
        entries = JournalEntry.objects.filter(division=division, date__gte=retention_cutoff())
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        if start:
            entries = entries.filter(date__gte=datetime.combine(start, time.min, timezone.utc))
        if end:
            entries = entries.filter(date__lte=datetime.combine(end, time.max, timezone.utc))

        fields = [
            "entry_id",
            "date",
            "ref_type",
            "amount",
            "balance",
            "reason",
            "description",
            "first_party_id",
            "second_party_id",
            "context_id",
            "context_id_type",
            "tax",
            "tax_receiver_id",
        ]

        def rows():
            writer = csv.writer(CsvBuffer())
            yield writer.writerow(
                [
                    "corporation_id",
                    "corporation_name",
                    "division",
                    *fields,
                    "same_corporation_transfer",
                ]
            )
            for entry in (
                entries.order_by("date", "entry_id").values(*fields).iterator(chunk_size=2000)
            ):
                values = []
                for field in fields:
                    value = entry[field]
                    if field == "date":
                        value = value.astimezone(timezone.utc).isoformat()
                    elif field in ("amount", "balance", "tax") and value is not None:
                        value = format(value, ".2f")
                    elif field in ("reason", "description", "context_id_type"):
                        value = safe_csv_text(value)
                    values.append(value)
                yield writer.writerow(
                    [
                        division.corporation.corporation_id,
                        safe_csv_text(division.corporation.name),
                        division.division,
                        *values,
                        is_internal_transfer(
                            entry, division.corporation.corporation_id, exclude_between=False
                        ),
                    ]
                )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="wallet-{division.corporation.corporation_id}'
            f'-{division.division}.csv"'
        )
        response["Cache-Control"] = "no-store"
        return response
    return render(request, "accountant/export.html", {"form": form, "cutoff": retention_cutoff()})


@login_required
@permission_required("accountant.manage_sources", raise_exception=True)
def sources(request):
    return render(
        request,
        "accountant/sources.html",
        {
            "corporations": Corporation.objects.prefetch_related("divisions"),
        },
    )


@login_required
@permission_required("accountant.manage_sources", raise_exception=True)
@token_required(scopes=SCOPES)
def connect(request, token):
    if (
        token.user_id != request.user.pk
        or not Token.objects.filter(pk=token.pk).require_scopes(SCOPES).exists()
    ):
        raise PermissionDenied
    # The SSO return is a GET. Present a CSRF-protected confirmation before saving a source.
    if request.method == "POST":
        try:
            corporation = authorize_corporation(token)
        except (EsiError, ValueError):
            messages.error(
                request,
                "Could not authorize this corporation. Check character roles and ESI availability.",
            )
        except Exception:
            messages.error(request, "Token validation failed. Try reauthorizing the character.")
        else:
            try:
                sync_wallets.delay(corporation.pk)
            except Exception:
                messages.warning(
                    request, "Corporation saved. Initial sync could not be queued; check Celery."
                )
            else:
                messages.success(request, f"{corporation.name} connected. Initial sync queued.")
        return redirect("accountant:sources")
    return render(
        request,
        "accountant/connect.html",
        {
            "character_name": token.character_name,
            "token_id": token.pk,
        },
    )


@login_required
@permission_required("accountant.manage_sources", raise_exception=True)
@require_POST
def sync(request, pk):
    corporation = get_object_or_404(Corporation, pk=pk, enabled=True)
    try:
        sync_wallets.delay(corporation.pk)
    except Exception:
        messages.error(request, "Could not queue synchronization. Check the Celery broker.")
    else:
        messages.success(request, f"Synchronization queued for {corporation.name}.")
    return redirect("accountant:sources")
