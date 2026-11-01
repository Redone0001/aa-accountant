from django.contrib.auth.models import Group
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

ref_validator = RegexValidator(r"^[a-z][a-z0-9_]*$", "Use the exact ESI ref_type identifier.")


class Corporation(models.Model):
    corporation_id = models.PositiveBigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    token = models.ForeignKey("esi.Token", null=True, blank=True, on_delete=models.SET_NULL)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        permissions = [
            ("manage_sources", "Can authorize and synchronize corporation wallets"),
            ("export_journal", "Can export visible corporation wallet history"),
        ]

    def __str__(self):
        return self.name


class WalletDivision(models.Model):
    corporation = models.ForeignKey(Corporation, on_delete=models.CASCADE, related_name="divisions")
    division = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    name = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("corporation__name", "division")
        constraints = [
            models.UniqueConstraint(
                fields=("corporation", "division"), name="acct_unique_division"
            ),
            models.CheckConstraint(
                condition=models.Q(division__gte=1, division__lte=7), name="acct_div_1_7"
            ),
        ]

    def __str__(self):
        return f"{self.corporation} / {self.division} {self.name}"


class JournalEntry(models.Model):
    division = models.ForeignKey(WalletDivision, on_delete=models.CASCADE, related_name="journal")
    entry_id = models.PositiveBigIntegerField()
    date = models.DateTimeField(db_index=True)
    ref_type = models.CharField(max_length=128, db_index=True)
    amount = models.DecimalField(max_digits=26, decimal_places=2, null=True, blank=True)
    balance = models.DecimalField(max_digits=26, decimal_places=2, null=True, blank=True)
    reason = models.TextField(blank=True)
    description = models.TextField(blank=True)
    first_party_id = models.PositiveBigIntegerField(null=True, blank=True)
    second_party_id = models.PositiveBigIntegerField(null=True, blank=True)
    context_id = models.BigIntegerField(null=True, blank=True)
    context_id_type = models.CharField(max_length=64, blank=True)
    tax = models.DecimalField(max_digits=26, decimal_places=2, null=True, blank=True)
    tax_receiver_id = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-date", "-entry_id")
        constraints = [
            models.UniqueConstraint(fields=("division", "entry_id"), name="acct_unique_entry"),
        ]
        indexes = [models.Index(fields=("division", "date"), name="acct_div_date")]


class DisplayMode(models.TextChoices):
    ROW = "row", "Separate row"
    OTHER = "other", "Bundle into Other"
    IGNORE = "ignore", "Ignore (exclude from totals)"


class IskUnit(models.TextChoices):
    FULL = "isk", "ISK (full amount)"
    MILLION = "million", "M. isk"
    BILLION = "billion", "B. isk"


class Dashboard(models.Model):
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    divisions = models.ManyToManyField(WalletDivision, related_name="dashboards")
    allowed_groups = models.ManyToManyField(
        Group,
        blank=True,
        help_text="Empty: all users with view_dashboard permission. Otherwise: these groups only.",
    )
    default_unit = models.CharField(max_length=10, choices=IskUnit.choices, default=IskUnit.BILLION)
    unconfigured_mode = models.CharField(
        max_length=6,
        choices=DisplayMode.choices,
        default=DisplayMode.OTHER,
        help_text="How to handle ref_types without a rule.",
    )
    exclude_between_selected_corporations = models.BooleanField(
        default=True,
        help_text="Exclude corporation account withdrawals between selected corporations. "
        "Same-corporation division transfers are always excluded.",
    )

    class Meta:
        ordering = ("name",)
        default_permissions = ("add", "change", "delete", "view")

    def __str__(self):
        return self.name

    @classmethod
    def visible_to(cls, user):
        if not user.has_perm("accountant.view_dashboard"):
            return cls.objects.none()
        if user.is_superuser:
            return cls.objects.all()
        return cls.objects.filter(
            models.Q(allowed_groups__isnull=True) | models.Q(allowed_groups__in=user.groups.all())
        ).distinct()


class ExcludedEntity(models.Model):
    class EntityType(models.TextChoices):
        CHARACTER = "character", "Character"
        CORPORATION = "corporation", "Corporation"

    dashboard = models.ForeignKey(
        Dashboard, on_delete=models.CASCADE, related_name="excluded_entities"
    )
    entity_id = models.PositiveBigIntegerField(
        validators=[MinValueValidator(1)],
        help_text="EVE character or corporation ID. Entries with this ID as either party "
        "are excluded from this dashboard, for every reference type.",
    )
    entity_type = models.CharField(
        max_length=11, choices=EntityType.choices, default=EntityType.CHARACTER
    )
    display_name = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("display_name", "entity_id")
        verbose_name_plural = "excluded entities"
        constraints = [
            models.UniqueConstraint(
                fields=("dashboard", "entity_id"), name="acct_unique_excluded_entity"
            ),
            models.CheckConstraint(
                condition=models.Q(entity_id__gte=1), name="acct_excluded_entity_positive"
            ),
        ]

    def __str__(self):
        identity = f"{self.get_entity_type_display()} #{self.entity_id}"
        return f"{self.display_name} ({identity})" if self.display_name else identity


class RefTypeRule(models.Model):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="ref_rules")
    ref_type = models.CharField(max_length=128, validators=[ref_validator])
    display_name = models.CharField(max_length=128)
    mode = models.CharField(max_length=6, choices=DisplayMode.choices, default=DisplayMode.ROW)
    split_reasons = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ("order", "display_name")
        constraints = [
            models.UniqueConstraint(fields=("dashboard", "ref_type"), name="acct_unique_ref_rule"),
        ]

    def __str__(self):
        return f"{self.dashboard}: {self.ref_type}"


class ReasonRule(models.Model):
    class MatchType(models.TextChoices):
        EXACT = "exact", "Exact (case-sensitive)"
        IEXACT = "iexact", "Exact (case-insensitive)"
        CONTAINS = "contains", "Contains (case-sensitive)"
        ICONTAINS = "icontains", "Contains (case-insensitive)"

    ref_rule = models.ForeignKey(RefTypeRule, on_delete=models.CASCADE, related_name="reason_rules")
    reason = models.CharField(
        max_length=512,
        help_text="Reason text or keyword, without quotes. Match type controls comparison; "
        "spaces are significant.",
    )
    match_type = models.CharField(max_length=9, choices=MatchType.choices, default=MatchType.EXACT)
    display_name = models.CharField(max_length=128)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ("order", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("ref_rule", "reason", "match_type"), name="acct_unique_reason_rule"
            ),
        ]

    def matches(self, reason):
        if not self.reason:
            return False
        text, pattern = reason or "", self.reason
        if self.match_type in (self.MatchType.IEXACT, self.MatchType.ICONTAINS):
            text, pattern = text.casefold(), pattern.casefold()
        if self.match_type in (self.MatchType.EXACT, self.MatchType.IEXACT):
            return text == pattern
        if self.match_type in (self.MatchType.CONTAINS, self.MatchType.ICONTAINS):
            return pattern in text
        return False

    def __str__(self):
        return self.display_name
