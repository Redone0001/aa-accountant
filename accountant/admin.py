from django import forms
from django.contrib import admin

from accountant.forms import RefTypeRuleForm
from accountant.models import (
    Corporation,
    Dashboard,
    ExcludedEntity,
    JournalEntry,
    ReasonRule,
    RefTypeRule,
    WalletDivision,
)


class DivisionInline(admin.TabularInline):
    model = WalletDivision
    extra = 0
    fields = ("division", "name", "enabled", "last_success", "last_error")
    readonly_fields = ("last_success", "last_error")


@admin.register(Corporation)
class CorporationAdmin(admin.ModelAdmin):
    list_display = ("name", "corporation_id", "enabled")
    readonly_fields = ("corporation_id", "name", "token")
    inlines = (DivisionInline,)

    def has_add_permission(self, request):
        return False  # Use the SSO connect flow to verify corporation access.


@admin.register(WalletDivision)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("corporation", "division", "name", "enabled", "last_success", "last_error")
    list_filter = ("corporation", "enabled")
    readonly_fields = ("last_attempt", "last_success", "last_error")


class RefInline(admin.TabularInline):
    model = RefTypeRule
    form = RefTypeRuleForm
    extra = 0
    show_change_link = True


class ExcludedEntityInline(admin.TabularInline):
    model = ExcludedEntity
    fields = ("entity_type", "entity_id", "display_name")
    extra = 0


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("name", "default_unit", "unconfigured_mode")
    filter_horizontal = ("divisions", "allowed_groups")
    inlines = (RefInline, ExcludedEntityInline)


@admin.register(ExcludedEntity)
class ExcludedEntityAdmin(admin.ModelAdmin):
    list_display = ("display_name", "entity_type", "entity_id", "dashboard")
    list_filter = ("dashboard", "entity_type")
    search_fields = ("display_name", "=entity_id")


class ReasonRuleForm(forms.ModelForm):
    class Meta:
        model = ReasonRule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].strip = False
        self.fields["display_name"].help_text = (
            "Rules with the same display name merge into one row within this reference type. "
            "Use identical spelling and capitalization."
        )


class ReasonInline(admin.TabularInline):
    model = ReasonRule
    form = ReasonRuleForm
    fields = ("reason", "match_type", "display_name", "order")
    extra = 0


@admin.register(RefTypeRule)
class RefRuleAdmin(admin.ModelAdmin):
    form = RefTypeRuleForm
    list_display = ("display_name", "dashboard", "ref_type", "mode", "split_reasons")
    list_filter = ("dashboard", "mode")
    inlines = (ReasonInline,)


@admin.register(JournalEntry)
class JournalAdmin(admin.ModelAdmin):
    list_display = ("date", "division", "ref_type", "amount", "reason")
    list_filter = ("division", "ref_type")
    search_fields = ("reason", "description", "=entry_id")
    readonly_fields = [field.name for field in JournalEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
