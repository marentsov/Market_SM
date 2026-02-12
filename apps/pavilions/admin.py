from django import forms
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.db.models import Count
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.http import HttpResponse
from .models import (
    Building, Pavilion, Tenant, Contract,
    ProductCategory, ElectricityMeter, ElectricityReading
)
from .services.meter_importer import MeterImporter
from .services.excel_import import import_excel
from .services.contracts_importer import ContractsImporter


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'pavilions_count', 'created_at']
    search_fields = ['name', 'address']
    list_per_page = 20

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_pavilions_count=Count('pavilions'))
        return queryset

    def pavilions_count(self, obj):
        return obj._pavilions_count

    pavilions_count.short_description = 'Кол-во павильонов'
    pavilions_count.admin_order_field = '_pavilions_count'


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'inn', 'phone', 'email', 'pavilions_count', 'created_at']
    search_fields = ['name', 'inn', 'phone', 'email']
    list_per_page = 50

    readonly_fields = ['pavilions_display']

    fieldsets = (
        (None, {
            'fields': ('name', 'inn', 'phone', 'email')
        }),
        ('Павильоны', {
            'fields': ('pavilions_display',),
            'description': 'Павильоны, связанные с этим арендатором',
        }),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_pavilions_count=Count('pavilion'))
        return queryset

    def pavilions_count(self, obj):
        return obj._pavilions_count

    pavilions_count.short_description = 'Кол-во павильонов'
    pavilions_count.admin_order_field = '_pavilions_count'

    def pavilions_display(self, obj):
        """Список павильонов, связанных с арендатором."""
        if not obj.pk:
            return "—"
        pavilions = obj.pavilion.all().select_related('building').order_by('building__name', 'name')
        if not pavilions:
            return "Нет связанных павильонов"
        links = [
            format_html(
                '<a href="/admin/pavilions/pavilion/{}/change/">{}</a>',
                p.id,
                f"{p.building.name} — {p.name}"
            )
            for p in pavilions[:50]
        ]
        result = format_html_join(', ', '{}', ((link,) for link in links))
        if pavilions.count() > 50:
            return format_html('{} ... (+{})', result, pavilions.count() - 50)
        return result

    pavilions_display.short_description = 'Павильоны'


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    list_per_page = 50


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'pavilions_count', 'created_at']
    search_fields = ['name']
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_pavilions_count=Count('pavilion_set'))
        return queryset

    def pavilions_count(self, obj):
        return obj._pavilions_count

    pavilions_count.short_description = 'Кол-во павильонов'
    pavilions_count.admin_order_field = '_pavilions_count'


class ProductCategoryInline(admin.TabularInline):
    """Категории товаров в павильоне"""
    model = Pavilion.product_categories.through
    extra = 1
    verbose_name = 'Категория товаров'
    verbose_name_plural = 'Категории товаров'


class PavilionAdminForm(forms.ModelForm):
    # Группировка тегов по категориям для удобного отображения
    TAGS_GROUPS = {
        'Этажность': [
            ('2_etazha', '2 этажа'),
            ('3_etazha', '3 этажа'),
            ('4_etazha', '4+ этажа'),
        ],
        'Крыша': [
            ('krysha_novaya', 'Новая'),
            ('krysha_horoshee', 'Хорошее состояние'),
            ('krysha_remont', 'Требует ремонта'),
        ],
        'Коммуникации': [
            ('gaz_est', 'Газ есть'),
            ('gaz_net', 'Газа нет'),
            ('voda_est', 'Вода есть'),
            ('voda_net', 'Воды нет'),
            ('otoplenie_central', 'Отопление центральное'),
            ('otoplenie_avtonom', 'Отопление автономное'),
            ('otoplenie_net', 'Отопления нет'),
            ('ventilacia_est', 'Вентиляция есть'),
            ('ventilacia_net', 'Вентиляции нет'),
        ],
        'Безопасность': [
            ('signalizacia_est', 'Сигнализация есть'),
            ('signalizacia_net', 'Сигнализации нет'),
        ],
        'Удобства': [
            ('rampa_est', 'Погрузочная рампа'),
            ('vitrina_est', 'Витрина'),
            ('otdelny_vhod', 'Отдельный вход'),
            ('parkovka', 'Парковка рядом'),
        ],
    }

    # Плоский список всех тегов для choices (технически нужно для поля)
    ALL_TAGS_CHOICES = []
    for group_choices in TAGS_GROUPS.values():
        ALL_TAGS_CHOICES.extend(group_choices)

    # Поле для тегов с чекбоксами
    tags = forms.MultipleChoiceField(
        label='Дополнительные характеристики',
        choices=ALL_TAGS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'vCheckboxSelectMultiple grouped-checkboxes'
        }),
        required=False,
        help_text='Выберите характеристики, подходящие для этого павильона'
    )

    class Media:
        css = {
            'all': ('admin/css/pavilion_tags.css',)
        }
        js = ('admin/js/pavilion_tags.js',)

    class Meta:
        model = Pavilion
        fields = '__all__'
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 3, 'class': 'vLargeTextField'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Добавляем информацию о группах в атрибуты виджета
        self.fields['tags'].widget.attrs['data-groups'] = str(self.TAGS_GROUPS)

        # Если редактируем существующий объект - загружаем его теги
        if self.instance.pk and self.instance.tags:
            self.initial['tags'] = self.instance.tags

    def clean_tags(self):
        """Валидация тегов если нужно"""
        tags = self.cleaned_data.get('tags', [])
        # Здесь можно добавить логику, например:
        # - нельзя выбрать одновременно "газ есть" и "газа нет"
        # - нельзя выбрать больше 10 тегов и т.д.
        return tags

    def save(self, commit=True):
        """Сохраняем выбранные теги в JSONField"""
        instance = super().save(commit=False)

        # Берём выбранные теги и сохраняем как список
        instance.tags = self.cleaned_data.get('tags', [])

        if commit:
            instance.save()
            # Если есть ManyToMany поля, сохраняем и их
            self.save_m2m()

        return instance


@admin.register(Pavilion)
class PavilionAdmin(admin.ModelAdmin):
    form = PavilionAdminForm
    change_list_template = "admin/pavilions/pavilion/change_list.html"

    list_display = ['name', 'building', 'row', 'area', 'status', 'display_tags']
    list_filter = ['building', 'status', 'tags']  # Фильтрация по тегам!
    search_fields = ['name', 'comment']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'building', 'row', 'area', 'status')
        }),
        ('Аренда', {
            'fields': ('contract', 'tenant', 'product_categories'),
            'classes': ('wide',),
        }),
        ('🏷️ Дополнительные характеристики', {
            'fields': ('tags',),
            'classes': ('wide',),
            'description': '''
                <div style="background: #e8f5e9; padding: 10px; border-left: 4px solid #2e7d32; margin-bottom: 15px;">
                    <strong>✓ Отметьте характеристики павильона</strong><br>
                    Просто поставьте галочки напротив подходящих пунктов
                </div>
            '''
        }),
        ('Прочее', {
            'fields': ('comment', 'created_at', 'updated_at'),
            'classes': ('collapse',),  # Скрыто по умолчанию
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def display_tags(self, obj):
        """Красивое отображение тегов в списке"""
        tags = obj.get_tags_display()
        if tags:
            if len(tags) > 5:
                return f"{', '.join(tags[:5])} (+{len(tags) - 5})"
            return ', '.join(tags)
        return '—'  # Просто тире, без HTML

    display_tags.short_description = 'Характеристики'
    display_tags.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-excel/', self.import_excel_view, name='import_excel'),
            path('import-contracts/', self.import_contracts_view, name='import_contracts'),
        ]
        return custom_urls + urls

    def import_excel_view(self, request):
        """Вью для импорта павильонов из Excel."""
        if request.method == 'POST' and request.FILES.get('excel_file'):
            excel_file = request.FILES['excel_file']
            try:
                total_in_file, created_count = import_excel(excel_file)
                messages.success(
                    request,
                    f'Успешно загружено! Файл содержит {total_in_file} павильонов. '
                    f'Добавлено {created_count} новых павильонов.'
                )
                return redirect('admin:pavilions_pavilion_changelist')
            except Exception as e:
                messages.error(request, f'Ошибка при загрузке: {str(e)}')
        context = dict(
            self.admin_site.each_context(request),
            title="Загрузить Excel с павильонами"
        )
        return render(request, 'admin/import_excel.html', context)

    def import_contracts_view(self, request):
        """Вью для импорта договоров и арендаторов из Excel."""
        if request.method == 'POST' and request.FILES.get('excel_file'):
            excel_file = request.FILES['excel_file']
            try:
                importer = ContractsImporter(excel_file)
                success = importer.import_data()
                stats = importer.get_stats()

                if success:
                    s = stats['stats']
                    messages.success(request, (
                        f"Импорт завершён! "
                        f"Создано арендаторов: {s['tenants_created']}, "
                        f"обновлено: {s['tenants_updated']}. "
                        f"Создано договоров: {s['contracts_created']}, "
                        f"обновлено: {s['contracts_updated']}. "
                        f"Обновлено павильонов: {s['pavilions_updated']}. "
                        f"Ненайденных павильонов: {stats['unmatched_count']}."
                    ))
                    if stats['unmatched_count'] > 0:
                        examples = s['unmatched_pavilions'][:5]
                        messages.warning(
                            request,
                            f"Павильоны не найдены (примеры): {', '.join(examples)}"
                        )
                else:
                    messages.error(request, "Ошибка при импорте")
                    for err in stats['errors'][:5]:
                        messages.error(request, err)

                return redirect('admin:pavilions_pavilion_changelist')
            except Exception as e:
                messages.error(request, f'Ошибка при загрузке: {str(e)}')

        context = dict(
            self.admin_site.each_context(request),
            title="Импорт договоров и арендаторов",
            help_text=self._get_contracts_import_help_text()
        )
        return render(request, 'admin/import_contracts.html', context)

    def _get_contracts_import_help_text(self):
        return """
        <div style="background: #f8f8f8; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3>📋 Требования к файлу</h3>
            <ul>
                <li>Лист: <strong>актуальные арендаторы</strong></li>
                <li>Колонки: <strong>Контрагент</strong>, <strong>ИНН</strong>, <strong>Договор</strong>, <strong>Объект</strong></li>
                <li>Контрагент → арендатор, Договор → договор, Объект → павильон</li>
                <li>Павильоны должны уже существовать (сначала импортируйте павильоны)</li>
            </ul>
        </div>
        """


class ElectricityReadingInline(admin.TabularInline):
    """Показания в счетчике"""
    model = ElectricityReading
    extra = 0
    fields = ['date', 'meter_reading', 'consumption', 'comment']
    readonly_fields = ['consumption', 'created_at']
    ordering = ['-date']


@admin.register(ElectricityMeter)
class ElectricityMeterAdmin(admin.ModelAdmin):
    change_list_template = "admin/pavilions/electricitymeter/change_list.html"
    list_display = [
        'meter_number',
        'pavilion_link',
        'serial_number',
        'location',
        'last_verified_hours_ago',
        'current_reading_display',
        'last_reading_date_display'
    ]

    list_filter = ['pavilions__building']
    search_fields = ['meter_number', 'serial_number', 'pavilions__name']
    list_per_page = 50

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('pavilions', 'meter_number', 'serial_number')
        }),
        ('Дополнительно', {
            'fields': ('location', 'last_verified_hours_ago', 'comment'),
            'classes': ('collapse',)
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ElectricityReadingInline]

    # ДОБАВЛЯЕМ ССЫЛКУ НА ИМПОРТ СЧЕТЧИКОВ
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-meters/', self.import_meters_view, name='import_meters'),
        ]
        return custom_urls + urls

    def import_meters_view(self, request):
        """
        Вью для импорта счетчиков из Excel
        """
        if request.method == 'POST' and request.FILES.get('excel_file'):
            excel_file = request.FILES['excel_file']

            try:
                # Импортируем данные
                importer = MeterImporter(excel_file)
                success = importer.import_data()
                stats = importer.get_stats()

                if success:
                    # Показываем статистику
                    messages.success(request, f"""
                        Импорт завершен успешно!
                        Обработано листов: {stats['stats']['sheets_processed']}
                        Создано счетчиков: {stats['stats']['meters_created']}
                        Обновлено счетчиков: {stats['stats']['meters_updated']}
                        Создано показаний: {stats['stats']['readings_created']}
                        Ненайденных павильонов: {stats['unmatched_count']}
                    """)

                    # Если есть ненайденные павильоны
                    if stats['unmatched_count'] > 0:
                        messages.warning(request,
                                         f"Найдено {stats['unmatched_count']} ненайденных павильонов. "
                                         "Проверьте названия павильонов в файле."
                                         )
                        # Показываем первые 5 ненайденных павильонов
                        if hasattr(importer, 'stats') and importer.stats.get('unmatched_pavilions'):
                            unmatched = importer.stats['unmatched_pavilions'][:5]
                            messages.info(request,
                                          f"Примеры ненайденных павильонов: {', '.join(unmatched)}"
                                          )

                    # Показываем ошибки (первые 5)
                    if stats['errors']:
                        for error in stats['errors'][:5]:
                            messages.error(request, error)
                        if len(stats['errors']) > 5:
                            messages.error(request, f"... и еще {len(stats['errors']) - 5} ошибок")

                    # Если сформирован файл отчета об ошибках
                    if stats.get('has_error_report') and stats.get('error_report_path'):
                        messages.warning(
                            request,
                            f"Создан файл с ненайденными павильонами (папка media): {stats['error_report_path']}"
                        )

                else:
                    messages.error(request, "Ошибка при импорте файла")
                    if stats['errors']:
                        for error in stats['errors'][:10]:
                            messages.error(request, error)

                return redirect('admin:pavilions_electricitymeter_changelist')

            except Exception as e:
                messages.error(request, f'Ошибка при загрузке: {str(e)}')

        # Шаблон для загрузки файла
        context = dict(
            self.admin_site.each_context(request),
            title="Импорт счетчиков из Excel",
            help_text=self._get_import_help_text()
        )
        return render(request, 'admin/import_meters.html', context)

    def _get_import_help_text(self):
        """
        Текст с инструкциями для импорта
        """
        return """
        <div style="background: #f8f8f8; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3>📋 Инструкция по загрузке счетчиков:</h3>
            <p><strong>Требования к файлу:</strong></p>
            <ul>
                <li>Файл должен быть в формате Excel (.xlsx)</li>
                <li>Листы должны называться: <strong>"показания ДД.ММ.ГГГГ"</strong></li>
                <li>Примеры названий листов:
                    <ul>
                        <li>"показания 25.12.2025"</li>
                        <li>"показания 05.02.2026"</li>
                    </ul>
                </li>
                <li>Каждый лист должен содержать следующие колонки:
                    <ol>
                        <li><strong>№ счетчика</strong> - номер счетчика</li>
                        <li><strong>Серийник</strong> - серийный номер</li>
                        <li><strong>Показания</strong> - текущие показания</li>
                        <li><strong>Расположение</strong> - название павильона (должно совпадать с именем павильона в системе)</li>
                        <li><strong>Проверено часов назад</strong> - количество часов с последней проверки</li>
                    </ol>
                </li>
                <li>Если в колонке "Проверено часов назад" значение больше 168, 
                    в колонке "Показания" будет написано "Не на связи больше 168 часов"</li>
            </ul>
            <p><strong>Что будет сделано:</strong></p>
            <ul>
                <li>Счетчики будут созданы или обновлены</li>
                <li>Показания будут добавлены под соответствующей датой</li>
                <li>Счетчики будут привязаны к павильонам по названию в колонке "Расположение"</li>
                <li>Счетчики, которые не удалось привязать, будут записаны в отчет об ошибках</li>
            </ul>
        </div>
        """

    def pavilion_link(self, obj):
        pavilions = list(obj.pavilions.all()[:5])
        if not pavilions:
            return "—"
        links = format_html_join(
            ', ',
            '<a href="/admin/pavilions/pavilion/{}/change/">{}</a>',
            ((p.id, p.name) for p in pavilions)
        )
        count = obj.pavilions.count()
        if count > 5:
            return format_html('{}, +{}', links, count - 5)
        return links

    pavilion_link.short_description = 'Павильоны'

    def current_reading_display(self, obj):
        reading = obj.current_reading
        if reading:
            return f"{reading} кВт·ч"
        return "-"

    current_reading_display.short_description = 'Текущие показания'

    def last_reading_date_display(self, obj):
        date = obj.last_reading_date
        if date:
            return date.strftime('%d.%m.%Y')
        return "-"

    last_reading_date_display.short_description = 'Дата последних показаний'


@admin.register(ElectricityReading)
class ElectricityReadingAdmin(admin.ModelAdmin):
    list_display = [
        'meter_link',
        'date',
        'meter_reading',
        'consumption',
        'created_at'
    ]

    list_filter = ['date', 'meter__pavilions__building']
    search_fields = ['meter__meter_number', 'meter__pavilions__name']
    date_hierarchy = 'date'
    list_per_page = 50

    readonly_fields = ['consumption', 'created_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('meter', 'date', 'meter_reading', 'consumption')
        }),
        ('Дополнительно', {
            'fields': ('comment', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def meter_link(self, obj):
        return format_html(
            '<a href="/admin/pavilions/electricitymeter/{}/change/">{}</a>',
            obj.meter.id,
            obj.meter.meter_number
        )

    meter_link.short_description = 'Счетчик'
    meter_link.admin_order_field = 'meter__meter_number'
