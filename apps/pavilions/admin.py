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
    list_display = ['name', 'phone', 'email', 'pavilions_count', 'created_at']
    search_fields = ['name', 'phone', 'email']
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(_pavilions_count=Count('pavilion_set'))
        return queryset

    def pavilions_count(self, obj):
        return obj._pavilions_count

    pavilions_count.short_description = 'Кол-во павильонов'
    pavilions_count.admin_order_field = '_pavilions_count'


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


@admin.register(Pavilion)
class PavilionAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'building_link',
        'row',
        'area',
        'status_display',
        'tenant_link',
        'meters_count',
        'created_at'
    ]

    list_filter = ['status', 'building', 'row', 'created_at']
    search_fields = ['name', 'row', 'comment']
    list_per_page = 100

    readonly_fields = ['created_at', 'updated_at', 'meters_display']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'building', 'row', 'area', 'status')
        }),
        ('Аренда', {
            'fields': ('tenant', 'contract'),
            'classes': ('collapse',)
        }),
        ('Счетчики', {
            'fields': ('meters_display',),
            'classes': ('collapse',),
            'description': 'Счетчики, привязанные к этому павильону',
        }),
        ('Дополнительно', {
            'fields': ('comment', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ProductCategoryInline]

    def meters_display(self, obj):
        """Список счетчиков, привязанных к павильону."""
        if not obj.pk:
            return "—"
        meters = ElectricityMeter.objects.filter(pavilions=obj).order_by('meter_number')
        if not meters:
            return "Нет привязанных счетчиков"
        links = [
            format_html('<a href="/admin/pavilions/electricitymeter/{}/change/">{}</a>', m.id, m.meter_number)
            for m in meters[:50]
        ]
        result = format_html_join(', ', '{}', ((link,) for link in links))
        if meters.count() > 50:
            return format_html('{} ... (+{})', result, meters.count() - 50)
        return result

    meters_display.short_description = 'Счетчики'

    # ДОБАВЛЯЕМ ССЫЛКУ НА ИМПОРТ ПАВИЛЬОНОВ
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-excel/', self.import_excel_view, name='import_excel'),
        ]
        return custom_urls + urls

    def import_excel_view(self, request):
        """
        Вью для импорта павильонов из Excel
        """
        if request.method == 'POST' and request.FILES.get('excel_file'):
            excel_file = request.FILES['excel_file']

            try:
                # ЗАГРУЗКА EXCEL
                total_in_file, created_count = import_excel(excel_file)

                messages.success(
                    request,
                    f'Успешно загружено! Файл содержит {total_in_file} павильонов. '
                    f'Добавлено {created_count} новых павильонов.'
                )
                return redirect('admin:pavilions_pavilion_changelist')

            except Exception as e:
                messages.error(request, f'Ошибка при загрузке: {str(e)}')

        # Шаблон для загрузки файла
        context = dict(
            self.admin_site.each_context(request),
            title="Загрузить Excel с павильонами"
        )
        return render(request, 'admin/import_excel.html', context)

    def building_link(self, obj):
        return format_html(
            '<a href="/admin/pavilions/building/{}/change/">{}</a>',
            obj.building.id,
            obj.building.name
        )

    building_link.short_description = 'Здание'
    building_link.admin_order_field = 'building__name'

    def tenant_link(self, obj):
        if obj.tenant:
            return format_html(
                '<a href="/admin/pavilions/tenant/{}/change/">{}</a>',
                obj.tenant.id,
                obj.tenant.name
            )
        return "-"

    tenant_link.short_description = 'Арендатор'
    tenant_link.admin_order_field = 'tenant__name'

    def status_display(self, obj):
        colors = {
            'free': 'green',
            'rented': 'orange',
            'reserved': 'blue',
            'repair': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_display.short_description = 'Статус'

    def meters_count(self, obj):
        return obj.electricity_meters.count()

    meters_count.short_description = 'Счетчиков'


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
