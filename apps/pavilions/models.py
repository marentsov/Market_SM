from decimal import Decimal

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

User = get_user_model()


class Building(models.Model):
    """Здание/рынок/территория"""
    name = models.CharField(
        'Название здания/рынка/территории',
        max_length=200,
        unique=True
    )
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
    inn = models.CharField('ИНН', max_length=20, blank=True, db_index=True)
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
    name = models.CharField('Название категории', max_length=100, unique=True)
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
        default=45.00,
        validators=[MinValueValidator(0)]
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
        verbose_name='Арендатор',
        related_name='pavilion'
    )

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

    TAG_CHOICES = [
        ('2_etazha', '2 этажа'),
        ('3_etazha', '3 этажа'),
        ('4_etazha', '4+ этажа'),
        ('krysha_novaya', 'Крыша новая'),
        ('krysha_horoshee', 'Крыша хорошее'),
        ('krysha_remont', 'Крыша требует ремонта'),
        ('gaz_est', 'Газ есть'),
        ('gaz_net', 'Газа нет'),
        ('voda_est', 'Вода есть'),
        ('voda_net', 'Воды нет'),
        ('otoplenie_central', 'Отопление центральное'),
        ('otoplenie_avtonom', 'Отопление автономное'),
        ('otoplenie_net', 'Отопления нет'),
        ('ventilacia_est', 'Вентиляция есть'),
        ('ventilacia_net', 'Вентиляции нет'),
        ('signalizacia_est', 'Сигнализация есть'),
        ('signalizacia_net', 'Сигнализации нет'),
        ('rampa_est', 'Погрузочная рампа'),
        ('vitrina_est', 'Витрина'),
        ('otdelny_vhod', 'Отдельный вход'),
        ('parkovka', 'Парковка рядом'),
    ]

    tags = models.JSONField(
        'Теги павильона',
        default=list,
        blank=True,
        help_text='Дополнительные характеристики павильона'
    )

    def get_tags_display(self):
        """Получить читаемые названия тегов"""
        display_dict = dict(self.TAG_CHOICES)
        return [display_dict.get(tag, tag) for tag in self.tags]

    def __str__(self):
        return f'{self.building.name} - {self.name}'

    @property
    def is_occupied(self):
        return self.status in ['rented', 'reserved']

    @property
    def meters_count(self):
        return self.electricity_meters.count()


class ElectricShield(models.Model):
    """Электрощиток, к которому подключены счётчики."""
    name = models.CharField('Название щита', max_length=100, unique=True)
    description = models.TextField('Описание', blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Электрощиток'
        verbose_name_plural = 'Электрощитки'
        ordering = ['name']

    def __str__(self):
        return self.name


class ElectricityMeter(models.Model):
    """
    Счетчик электроэнергии.
    У одного павильона может быть несколько счетчиков.
    Один счетчик может обслуживать несколько павильонов (например, общий на Е10/1 и Е10/2).
    """
    pavilions = models.ManyToManyField(
        Pavilion,
        verbose_name='Павильоны',
        related_name='electricity_meters',
        blank=True,
        help_text='Павильоны, которые обслуживает этот счетчик'
    )

    electric_shield = models.ForeignKey(
        ElectricShield,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Электрощиток',
        related_name='meters',
        help_text='К какому электрощиту подключён этот счётчик'
    )

    # Основные данные счетчика
    meter_number = models.CharField(
        'Номер счетчика',
        max_length=50,
        db_index=True,
        help_text='Номер по документам'
    )

    serial_number = models.CharField(
        'Серийный номер',
        max_length=100,
        blank=True,
        db_index=True,
        help_text='Серийный номер производителя'
    )

    # Расположение счетчика
    location = models.CharField(
        'Расположение',
        max_length=200,
        blank=True,
        help_text='Где установлен счетчик'
    )

    # Часов с последней проверки
    last_verified_hours_ago = models.IntegerField(
        'Часов с последней проверки',
        null=True,
        blank=True,
        help_text='Сколько часов прошло с последней проверки'
    )

    comment = models.TextField('Примечания', blank=True)

    created_at = models.DateTimeField('Дата создания записи', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Счетчик электроэнергии'
        verbose_name_plural = 'Счетчики электроэнергии'
        ordering = ['meter_number']
        constraints = [
            models.UniqueConstraint(
                fields=['meter_number'],
                name='unique_meter_number'
            ),
        ]

    def __str__(self):
        names = ', '.join(p.name for p in self.pavilions.all()[:3])
        if self.pavilions.count() > 3:
            names += f' (+{self.pavilions.count() - 3})'
        return f'Счетчик {self.meter_number} ({names or "—"})'

    @property
    def current_reading(self):
        """Последнее показание счетчика"""
        last_reading = self.readings.order_by('-date').first()
        return last_reading.meter_reading if last_reading else None

    @property
    def last_reading_date(self):
        """Дата последнего показания"""
        last_reading = self.readings.order_by('-date').first()
        return last_reading.date if last_reading else None


class ElectricityReading(models.Model):
    """
    Показания счетчика электроэнергии
    У каждого счетчика может быть много показаний
    """
    meter = models.ForeignKey(
        ElectricityMeter,
        on_delete=models.CASCADE,
        verbose_name='Счетчик',
        related_name='readings'
    )

    date = models.DateField('Дата снятия показаний', db_index=True)

    meter_reading = models.DecimalField(
        'Показания счетчика (кВт·ч)',
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    # Рассчитываемое поле - потребление за период
    consumption = models.DecimalField(
        'Потребление за период (кВт·ч)',
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Рассчитывается автоматически'
    )

    comment = models.TextField('Комментарий', blank=True)

    created_at = models.DateTimeField('Дата создания записи', auto_now_add=True)

    class Meta:
        verbose_name = 'Показание счетчика'
        verbose_name_plural = 'Показания счетчиков'
        ordering = ['-date', 'meter']
        unique_together = ['meter', 'date']
        indexes = [
            models.Index(fields=['meter', 'date']),
        ]

    def __str__(self):
        return f'{self.meter.meter_number} - {self.date}: {self.meter_reading} кВт·ч'

    def save(self, *args, **kwargs):
        # Автоматически рассчитываем потребление
        if not self.consumption:
            # Находим предыдущее показание для этого счетчика
            previous_reading = ElectricityReading.objects.filter(
                meter=self.meter,
                date__lt=self.date
            ).order_by('-date').first()

            if previous_reading:
                # Приводим к Decimal, т.к. внешние импорты могут передавать float
                current_value = self.meter_reading
                if not isinstance(current_value, Decimal):
                    current_value = Decimal(str(current_value))

                prev_value = previous_reading.meter_reading
                if not isinstance(prev_value, Decimal):
                    prev_value = Decimal(str(prev_value))

                self.consumption = current_value - prev_value
            else:
                self.consumption = Decimal("0")

        super().save(*args, **kwargs)