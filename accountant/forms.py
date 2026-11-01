from django import forms
from django.utils.timezone import now

from accountant.models import IskUnit, RefTypeRule
from accountant.ref_types import REF_TYPE_CHOICES, REF_TYPE_NAMES, ref_type_display_name


class RefTypeSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        option["attrs"]["data-display-name"] = ref_type_display_name(value) if value else ""
        return option


class RefTypeRuleForm(forms.ModelForm):
    ref_type = forms.ChoiceField(
        choices=[("", "Choose a reference type"), *REF_TYPE_CHOICES],
        widget=RefTypeSelect,
        label="Reference type",
    )
    display_name = forms.CharField(
        max_length=128,
        required=False,
        help_text="Defaults to the selected type's display name. You can customize it.",
    )

    class Meta:
        model = RefTypeRule
        fields = "__all__"

    class Media:
        js = ("accountant/admin-ref-types.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = self.instance.ref_type
        if self.instance.pk and existing not in REF_TYPE_NAMES:
            # Existing custom rules remain editable when upgrading from the text field.
            self.fields["ref_type"].choices = [
                *self.fields["ref_type"].choices,
                (existing, f"{ref_type_display_name(existing)} ({existing}) — existing value"),
            ]

    def clean_display_name(self):
        name = self.cleaned_data.get("display_name")
        ref_type = self.cleaned_data.get("ref_type", "")
        return name or ref_type_display_name(ref_type)


class ReportForm(forms.Form):
    year = forms.IntegerField(min_value=2003, max_value=2100)
    unit = forms.ChoiceField(choices=IskUnit.choices)

    def __init__(self, *args, dashboard, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.update(year=now().year, unit=dashboard.default_unit)


class ExportForm(forms.Form):
    division = forms.ModelChoiceField(queryset=None, label="Corporation / wallet division")
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, divisions, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["division"].queryset = divisions

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and start > end:
            raise forms.ValidationError("Start date must be on or before the end date.")
        return cleaned
