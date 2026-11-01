from django import forms
from django.utils.timezone import now

from accountant.models import IskUnit


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
