from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Building(models.Model):
    """Здание/рынок/территория"""
    name = models.CharField('Название здания/рынка/территории',
                            max_length=200, unique=True)
    address = models.TextField('Адрес', blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Здание/Рынок/Территория'
        verbose_name_plural = 'Здания/Рынки/Территории'
        ordering = ['name']

    def __str__(self):
        return self.name



class Tenant(models.Model):
    """Арендатор"""
    name = models.CharField('Название компании/ФИО', max_length=300)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    created_at = models.DateTimeField('Дата регистрации', auto_now_add=True)

    class Meta:
        verbose_name = 'Арендатор'
        verbose_name_plural = 'Арендаторы'
        ordering = ['name']

    def __str__(self):
        return self.name



class Contract(models.Model):
    """Договор аренды"""
    name = models.CharField('Название договора', max_length=200)
    contract_file = models.FileField(
        'Файл договора',
        upload_to='contracts/',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Договор аренды'
        verbose_name_plural = 'Договоры аренды'


    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    """Категория товаров (ключевые слова)"""
    name = models.CharField('Назване категории', max_length=100, unique=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Категория товаров'
        verbose_name_plural = 'Категории товаров'
        ordering = ['name']


    def __str__(self):
        return self.name



class Pavilion(models.Model):
    """Торговый павильон"""

    name = models.CharField('Название павильона', max_length=200)
    building = models.ForeignKey(
        Building,
        on_delete=models.PROTECT,
        verbose_name='Здание/Рынок/Территория',
        related_name='pavilions'
    )
    row = models.CharField('Ряд', max_length=100, blank=True)
    area = models.DecimalField(
        'Площадь (кв.м.)',
        max_digits=8,
        decimal_places=2,
        default=45.00
    )

    STATUS_CHOICES = [
        ('free', 'Свободен'),
        ('rented', 'Арендован'),
        ('reserved', 'Забронирован'),
        ('repair', 'На ремонте'),
    ]

    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default='free'
    )

    contract = models.ForeignKey(
        Contract,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Договор аренды'
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Арендатор'
    )

    electricity_meter_number = models.CharField('Номер счетчика', max_length=50, blank=True)

    product_categories = models.ManyToManyField(
        ProductCategory,
        verbose_name='Категории товаров',
        blank=True
    )

    comment = models.TextField('Комментарий', blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Павильон'
        verbose_name_plural = 'Павильоны'
        ordering = ['building', 'row', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['building', 'name'],
                name='unique_pavilion_per_building'
            )
        ]

    def __str__(self):
        return f'{self.building.name} - {self.name}'

    @property
    def is_occupied(self):
        return self.status in ['rented', 'reserved']


class ElectricityConsumption(models.Model):
    """Потребление электроэнергии"""
    pavilion = models.ForeignKey(
        Pavilion,
        on_delete=models.CASCADE,
        verbose_name='Павильон',
        related_name='electricity_consumptions'
    )
    date = models.DateField('Дата')
    meter_reading = models.DecimalField(
        'Показания счетчика (кВт ч)',
        max_digits=20,
        decimal_places=2
    )
    consumption = models.DecimalField(
        'Потребление (кВТ ч)',
        max_digits=20,
        decimal_places=2,
        help_text='Разница с предыдущим периодом'
    )
    created_at = models.DateTimeField('Дата создания записи', auto_now_add=True)

    class Meta:
        verbose_name = 'Потребление электроэнергии'
        verbose_name_plural = 'Потребление электроэнергии'
        ordering = ['-date']
        unique_together = ['pavilion', 'date']

    def __str__(self):
        return f'{self.pavilion.name} - {self.date}: {self.consumption} кВт ч'
    # Create your models here.
