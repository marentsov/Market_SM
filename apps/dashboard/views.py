from decimal import Decimal

from django.views.generic import TemplateView
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
            'occupancy_rate': round(occupancy_rate, 1),
        })

        return context
