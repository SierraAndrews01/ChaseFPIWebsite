from django import forms


class DateForm(forms.Form):
    date = forms.DateTimeField(input_formats=['%m/%d/%Y'], label="", widget=forms.TextInput(attrs={'id': 'datepicker'}))
