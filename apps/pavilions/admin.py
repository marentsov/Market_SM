from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.utils.html import format_html

from .models import Building, Pavilion, Tenant, Contract, ProductCategory, ElectricityConsumption
from .services.excel_import import import_excel

class BuildingAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'pavilions_count', 'occupied_pavilions_count']
    search_fields = ['name', 'address']
    list_per_page = 20

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            total_pavilions=Count('pavilions'),
            occupied_pavilions=Count('pavilions', filter=Q(pavilions__status__in=['rented', 'reserved']))
        )
        return queryset

    def pavilions_count(self, obj):
        return obj.total_pavilions

    pavilions_count.short_description = 'Всего павильонов'
    pavilions_count.admin_order_field = 'total_pavilions'

    def occupied_pavilions_count(self, obj):
        return obj.occupied_pavilions

    occupied_pavilions_count.short_description = 'Занято'
    occupied_pavilions_count.admin_order_field = 'occupied_pavilions'


class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'pavilions_count']
    search_fields = ['name', 'phone', 'email']
    list_filter = ['created_at']
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(active_pavilions=Count('pavilion'))
        return queryset

    def pavilions_count(self, obj):
        return obj.active_pavilions

    pavilions_count.short_description = 'Арендовано павильонов'


class ContractAdmin(admin.ModelAdmin):
    list_display = ['name', 'pavilion_link', 'created_at']
    search_fields = ['name', 'pavilion__name']
    list_filter = ['created_at']
    list_per_page = 50
    readonly_fields = ['created_at']

    def pavilion_link(self, obj):
        if obj.pavilion_set.exists():
            pavilion = obj.pavilion_set.first()
            return format_html('<a href="/admin/pavilions/pavilion/{}/change/">{}</a>',
                               pavilion.id, pavilion.name)
        return "-"

    pavilion_link.short_description = 'Павильон'


class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'pavilions_count', 'created_at']
    search_fields = ['name']
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(pavilion_count=Count('pavilion'))
        return queryset

    def pavilions_count(self, obj):
        return obj.pavilion_count

    pavilions_count.short_description = 'Кол-во павильонов'
    pavilions_count.admin_order_field = 'pavilion_count'


class ElectricityConsumptionInline(admin.TabularInline):
    model = ElectricityConsumption
    extra = 0
    readonly_fields = ['created_at']
    fields = ['date', 'meter_reading', 'consumption', 'created_at']
    ordering = ['-date']


class ProductCategoryInline(admin.TabularInline):
    model = Pavilion.product_categories.through
    extra = 1
    verbose_name = 'Категория товаров'
    verbose_name_plural = 'Категории товаров'


class PavilionAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'building_link',
        'row',
        'area',
        'status_display',
        'tenant_link',
        'electricity_meter_number',
        'created_at',
        'status'
    ]

    list_filter = [
        'status',
        'building',
        'row',
        'created_at',
        'updated_at',
    ]

    search_fields = [
        'name',
        'row',
        'electricity_meter_number',
        'comment',
        'building__name',
        'tenant__name',
    ]

    list_editable = ['row', 'area', 'status']

    list_per_page = 100

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'building', 'row', 'area', 'status')
        }),
        ('Аренда', {
            'fields': ('tenant', 'contract'),
            'classes': ('collapse',)
        }),
        ('Электричество', {
            'fields': ('electricity_meter_number',),
            'classes': ('collapse',)
        }),
        ('Дополнительно', {
            'fields': ('comment', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ProductCategoryInline, ElectricityConsumptionInline]

    actions = ['mark_as_free', 'mark_as_rented', 'export_as_csv']

    def building_link(self, obj):
        return format_html('<a href="/admin/pavilions/building/{}/change/">{}</a>',
                           obj.building.id, obj.building.name)

    building_link.short_description = 'Здание'
    building_link.admin_order_field = 'building__name'

    def tenant_link(self, obj):
        if obj.tenant:
            return format_html('<a href="/admin/pavilions/tenant/{}/change/">{}</a>',
                               obj.tenant.id, obj.tenant.name)
        return "-"

    tenant_link.short_description = 'Арендатор'
    tenant_link.admin_order_field = 'tenant__name'

    def status_display(self, obj):
        status_colors = {
            'free': 'green',
            'rented': 'orange',
            'reserved': 'blue',
            'repair': 'red',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_display.short_description = 'Статус'

    def mark_as_free(self, request, queryset):
        updated = queryset.update(status='free', tenant=None, contract=None)
        self.message_user(request, f'{updated} павильонов отмечены как свободные')

    mark_as_free.short_description = "Отметить как свободные"

    def mark_as_rented(self, request, queryset):
        updated = queryset.update(status='rented')
        self.message_user(request, f'{updated} павильонов отмечены как арендованные')

    mark_as_rented.short_description = "Отметить как арендованные"

    def export_as_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse
        from io import StringIO

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="pavilions.csv"'

        writer = csv.writer(response)
        writer.writerow(['Название', 'Здание', 'Ряд', 'Площадь', 'Статус', 'Арендатор', 'Номер счетчика'])

        for pavilion in queryset:
            writer.writerow([
                pavilion.name,
                pavilion.building.name,
                pavilion.row,
                pavilion.area,
                pavilion.get_status_display(),
                pavilion.tenant.name if pavilion.tenant else '',
                pavilion.electricity_meter_number
            ])

        return response

    export_as_csv.short_description = "Экспорт в CSV"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-excel/', self.import_excel_view, name='import_excel'),
        ]
        return custom_urls + urls

    def import_excel_view(self, request):
        """
        ПРОСТОЙ ВЬЮ ДЛЯ ЗАГРУЗКИ EXCEL
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


class ElectricityConsumptionAdmin(admin.ModelAdmin):
    list_display = ['pavilion_link', 'date', 'meter_reading', 'consumption', 'created_at']
    list_filter = ['date', 'pavilion__building']
    search_fields = ['pavilion__name', 'pavilion__electricity_meter_number']
    date_hierarchy = 'date'
    list_per_page = 50

    def pavilion_link(self, obj):
        return format_html('<a href="/admin/pavilions/pavilion/{}/change/">{}</a>',
                           obj.pavilion.id, obj.pavilion.name)

    pavilion_link.short_description = 'Павильон'
    pavilion_link.admin_order_field = 'pavilion__name'


# Регистрация моделей в админке
admin.site.register(Building, BuildingAdmin)
admin.site.register(Pavilion, PavilionAdmin)
admin.site.register(Tenant, TenantAdmin)
admin.site.register(Contract, ContractAdmin)
admin.site.register(ProductCategory, ProductCategoryAdmin)
admin.site.register(ElectricityConsumption, ElectricityConsumptionAdmin)
