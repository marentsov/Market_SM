from django import forms


class MeterImportForm(forms.Form):
    """
    Форма для импорта счетчиков из Excel
    """
    excel_file = forms.FileField(
        label='Excel файл со счетчиками',
        help_text='Файл должен содержать листы с названиями "показания ДД.ММ.ГГГГ"'
    )

    def clean_excel_file(self):
        file = self.cleaned_data['excel_file']

        # Проверяем расширение
        if not file.name.endswith(('.xlsx', '.xls')):
            raise forms.ValidationError("Файл должен быть в формате Excel (.xlsx или .xls)")

        # Проверяем размер (например, не более 10MB)
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Файл слишком большой. Максимальный размер 10MB")

        return file