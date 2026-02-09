.PHONY: run migrate makemigrations createsuperuser test shell

run:
	python manage.py runserver

migrate:
	python manage.py migrate

makemigrations:
	python manage.py makemigrations pavilions

createsuperuser:
	python manage.py createsuperuser

test:
	python manage.py test

shell:
	python manage.py shell

collectstatic:
	python manage.py collectstatic --noinput
