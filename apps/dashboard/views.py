from decimal import Decimal

from django.views.generic import TemplateView, ListView
from django.db.models import Count, Sum, Q, Exists, OuterRef, DecimalField
from django.db.models.functions import Coalesce

from apps.pavilions.models import (
    Building, Pavilion, Tenant, Contract,
    ElectricityMeter, ElectricityReading
)


class DashboardView(TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        pavilions = Pavilion.objects.all()
        buildings = Building.objects.all()
        tenants = Tenant.objects.all()
        contracts = Contract.objects.all()
        meters = ElectricityMeter.objects.all()

        total_pavilions = pavilions.count()
        total_buildings = buildings.count()
        total_tenants = tenants.count()
        total_contracts = contracts.count()
        total_meters = meters.count()

        pavilions_by_status = pavilions.values('status').annotate(
            count=Count('id')
        ).order_by('status')

        status_map = dict(Pavilion.STATUS_CHOICES)
        status_stats = {
            status_map.get(item['status'], item['status']): item['count']
            for item in pavilions_by_status
        }

        total_area = pavilions.aggregate(
            total=Coalesce(Sum('area'), Decimal('0'), output_field=DecimalField())
        )['total'] or Decimal('0')

        rented_pavilions = pavilions.filter(status='rented').count()
        free_pavilions = pavilions.filter(status='free').count()
        reserved_pavilions = pavilions.filter(status='reserved').count()
        repair_pavilions = pavilions.filter(status='repair').count()

        suspicious_readings = ElectricityReading.objects.filter(
            meter__pavilions=OuterRef('pk'),
            consumption__gt=Decimal('1')
        )
        suspicious_pavilions = pavilions.filter(
            Exists(suspicious_readings),
            tenant__isnull=True
        ).count()
        suspicious_pavilions_list = pavilions.filter(
            Exists(suspicious_readings),
            tenant__isnull=True
        ).select_related('building')[:10]

        top_tenants = tenants.annotate(
            pavilions_count=Count('pavilion')
        ).order_by('-pavilions_count')[:5]

        recent_readings = ElectricityReading.objects.select_related('meter').prefetch_related(
            'meter__pavilions'
        ).order_by('-date', '-id')[:10]

        buildings_stats = buildings.annotate(
            pavilions_count=Count('pavilions'),
            rented_count=Count('pavilions', filter=Q(pavilions__status='rented')),
            free_count=Count('pavilions', filter=Q(pavilions__status='free'))
        ).order_by('-pavilions_count')[:10]

        total_readings = ElectricityReading.objects.count()
        total_consumption = ElectricityReading.objects.aggregate(
            total=Coalesce(Sum('consumption'), Decimal('0'), output_field=DecimalField())
        )['total'] or Decimal('0')

        pavilions_with_meters = pavilions.filter(
            electricity_meters__isnull=False
        ).distinct().count()

        occupancy_rate = (
            (rented_pavilions / total_pavilions * 100) if total_pavilions > 0 else 0
        )

        context.update({
            'total_pavilions': total_pavilions,
            'total_buildings': total_buildings,
            'total_tenants': total_tenants,
            'total_contracts': total_contracts,
            'total_meters': total_meters,
            'total_readings': total_readings,
            'total_area': total_area,
            'rented_pavilions': rented_pavilions,
            'free_pavilions': free_pavilions,
            'reserved_pavilions': reserved_pavilions,
            'repair_pavilions': repair_pavilions,
            'suspicious_pavilions': suspicious_pavilions,
            'status_stats': status_stats,
            'buildings_stats': buildings_stats,
            'total_consumption': total_consumption,
            'pavilions_with_meters': pavilions_with_meters,
            'suspicious_pavilions_list': suspicious_pavilions_list,
            'top_tenants': top_tenants,
            'recent_readings': recent_readings,
            'occupancy_rate': round(occupancy_rate, 1),
        })

        return context


class PavilionListView(ListView):
    """
    Список павильонов с фильтрами, логика близка к админке.
    """
    model = Pavilion
    template_name = 'dashboard/pavilions_list.html'
    context_object_name = 'pavilions'
    paginate_by = 50

    def get_queryset(self):
        qs = Pavilion.objects.select_related('building', 'tenant', 'contract').prefetch_related(
            'electricity_meters'
        )

        request = self.request
        preset = request.GET.get('preset') or ''
        status = request.GET.get('status') or ''
        building_id = request.GET.get('building') or ''
        suspicious = request.GET.get('suspicious') or ''
        without_communication = request.GET.get('without_communication') or ''
        has_tenant = request.GET.get('has_tenant') or ''
        search = request.GET.get('q') or ''

        self._preset = preset
        self._status = status
        self._building_id = building_id
        self._suspicious = suspicious
        self._without_communication = without_communication
        self._has_tenant = has_tenant
        self._search = search

        # Преднастроенные фильтры (по клику с дашборда)
        if preset == 'rented':
            qs = qs.filter(status='rented')
        elif preset == 'free':
            qs = qs.filter(status='free')
        elif preset == 'reserved':
            qs = qs.filter(status='reserved')
        elif preset == 'repair':
            qs = qs.filter(status='repair')
        elif preset == 'suspicious':
            suspicious_readings = ElectricityReading.objects.filter(
                meter__pavilions=OuterRef('pk'),
                consumption__gt=Decimal('1')
            )
            qs = qs.filter(Exists(suspicious_readings), tenant__isnull=True)
        elif preset == 'without_communication':
            stale_meters = ElectricityMeter.objects.filter(
                Q(last_verified_hours_ago__gt=720) | Q(last_verified_hours_ago__isnull=True),
                pavilions=OuterRef('pk')
            )
            qs = qs.filter(Exists(stale_meters))

        # Дополнительные фильтры по параметрам
        if status:
            qs = qs.filter(status=status)

        if building_id:
            qs = qs.filter(building_id=building_id)

        if suspicious == 'yes' and preset != 'suspicious':
            suspicious_readings = ElectricityReading.objects.filter(
                meter__pavilions=OuterRef('pk'),
                consumption__gt=Decimal('1')
            )
            qs = qs.filter(Exists(suspicious_readings), tenant__isnull=True)

        if without_communication == 'yes' and preset != 'without_communication':
            stale_meters = ElectricityMeter.objects.filter(
                Q(last_verified_hours_ago__gt=720) | Q(last_verified_hours_ago__isnull=True),
                pavilions=OuterRef('pk')
            )
            qs = qs.filter(Exists(stale_meters))

        if has_tenant == 'yes':
            qs = qs.filter(tenant__isnull=False)
        elif has_tenant == 'no':
            qs = qs.filter(tenant__isnull=True)

        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(comment__icontains=search))

        return qs.order_by('building__name', 'row', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        querydict = self.request.GET.copy()
        if 'page' in querydict:
            querydict.pop('page')
        context['querystring'] = querydict.urlencode()

        context.update({
            'statuses': Pavilion.STATUS_CHOICES,
            'buildings': Building.objects.order_by('name'),
            'preset': getattr(self, '_preset', ''),
            'current_status': getattr(self, '_status', ''),
            'current_building_id': getattr(self, '_building_id', ''),
            'current_suspicious': getattr(self, '_suspicious', ''),
            'current_without_communication': getattr(self, '_without_communication', ''),
            'current_has_tenant': getattr(self, '_has_tenant', ''),
            'current_search': getattr(self, '_search', ''),
        })

        return context


class BuildingListView(ListView):
    model = Building
    template_name = 'dashboard/buildings_list.html'
    context_object_name = 'buildings'
    paginate_by = 50

    def get_queryset(self):
        qs = Building.objects.annotate(
            pavilions_count=Count('pavilions'),
            rented_count=Count('pavilions', filter=Q(pavilions__status='rented')),
            free_count=Count('pavilions', filter=Q(pavilions__status='free')),
        )
        search = self.request.GET.get('q') or ''
        self._search = search
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(address__icontains=search))
        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_search'] = getattr(self, '_search', '')
        return context


class TenantListView(ListView):
    model = Tenant
    template_name = 'dashboard/tenants_list.html'
    context_object_name = 'tenants'
    paginate_by = 50

    def get_queryset(self):
        qs = Tenant.objects.annotate(
            pavilions_count=Count('pavilion')
        )
        has_pavilions = self.request.GET.get('has_pavilions') or ''
        search = self.request.GET.get('q') or ''
        self._has_pavilions = has_pavilions
        self._search = search

        if has_pavilions == 'yes':
            qs = qs.filter(pavilions_count__gt=0)
        elif has_pavilions == 'no':
            qs = qs.filter(pavilions_count=0)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(inn__icontains=search) |
                Q(phone__icontains=search)
            )

        return qs.order_by('-pavilions_count', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_has_pavilions'] = getattr(self, '_has_pavilions', '')
        context['current_search'] = getattr(self, '_search', '')
        return context


class ContractListView(ListView):
    model = Contract
    template_name = 'dashboard/contracts_list.html'
    context_object_name = 'contracts'
    paginate_by = 50

    def get_queryset(self):
        qs = Contract.objects.annotate(
            pavilions_count=Count('pavilion')
        )
        search = self.request.GET.get('q') or ''
        self._search = search
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.order_by('-pavilions_count', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_search'] = getattr(self, '_search', '')
        return context


class MeterListView(ListView):
    model = ElectricityMeter
    template_name = 'dashboard/meters_list.html'
    context_object_name = 'meters'
    paginate_by = 50

    def get_queryset(self):
        qs = ElectricityMeter.objects.select_related().prefetch_related('pavilions')

        building_id = self.request.GET.get('building') or ''
        without_communication = self.request.GET.get('without_communication') or ''
        search = self.request.GET.get('q') or ''

        self._building_id = building_id
        self._without_communication = without_communication
        self._search = search

        if building_id:
            qs = qs.filter(pavilions__building_id=building_id)

        if without_communication == 'yes':
            qs = qs.filter(
                Q(last_verified_hours_ago__gt=720) | Q(last_verified_hours_ago__isnull=True)
            )

        if search:
            qs = qs.filter(
                Q(meter_number__icontains=search) |
                Q(serial_number__icontains=search)
            )

        return qs.order_by('meter_number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        querydict = self.request.GET.copy()
        if 'page' in querydict:
            querydict.pop('page')
        context['querystring'] = querydict.urlencode()

        context.update({
            'buildings': Building.objects.order_by('name'),
            'current_building_id': getattr(self, '_building_id', ''),
            'current_without_communication': getattr(self, '_without_communication', ''),
            'current_search': getattr(self, '_search', ''),
        })
        return context
