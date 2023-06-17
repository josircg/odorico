from django import forms


class ImportForm(forms.Form):
    arquivo = forms.FileField(label='', widget=forms.ClearableFileInput(attrs={'accept': '.csv'}), required=False)
