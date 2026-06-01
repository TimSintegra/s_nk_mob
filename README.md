## s-nk-mob

Django-приложение для ежедневных отчетов мастеров. Проект подготовлен для запуска в Docker с PostgreSQL.

## Что уже есть

- Django + Gunicorn
- PostgreSQL в `docker-compose.prod.yml`
- миграции применяются автоматически при старте контейнера
- статика собирается автоматически
- поддержка HTTPS за Traefik
- временный запуск по `SERVER_IP:9000`, если поддомен еще не настроен

## Что нужно для продакшена

- Ubuntu-сервер с Docker и Docker Compose
- доступ по SSH
- репозиторий на GitHub
- файл `.env.production`

## Подготовка `.env.production`

Создайте файл `.env.production` рядом с `docker-compose.prod.yml`:

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=SERVER_IP,mob.s-nk.su
DJANGO_CSRF_TRUSTED_ORIGINS=https://mob.s-nk.su
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True

POSTGRES_DB=s_nk_mob
POSTGRES_USER=s_nk_mob
POSTGRES_PASSWORD=replace-with-a-strong-db-password
POSTGRES_HOST=db
POSTGRES_PORT=5432

APP_DOMAIN=mob.s-nk.su
APP_PORT=9000
TRAEFIK_NETWORK=docker_proxy-server-net
```

Если поддомена пока нет, временно можно указать:

```env
DJANGO_ALLOWED_HOSTS=SERVER_IP
DJANGO_CSRF_TRUSTED_ORIGINS=
APP_DOMAIN=mob.s-nk.su
APP_PORT=9000
```

`APP_DOMAIN` нужен только для Traefik-маршрута по домену. Пока DNS не настроен, приложение можно использовать через порт `9000`.

## Деплой на сервер

```bash
ssh -p 2024 USER@SERVER_IP
cd /var/www
git clone YOUR_GITHUB_REPOSITORY s-nk-mob
cd s-nk-mob
cp .env.production.example .env.production
nano .env.production
docker compose -f docker-compose.prod.yml up -d --build
```

Проверка:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web
```

## Первый запуск

Создать администратора Django:

```bash
docker compose -f docker-compose.prod.yml exec web uv run python manage.py createsuperuser
```

Импортировать дерево работ из Excel:

```bash
docker compose -f docker-compose.prod.yml exec web uv run python manage.py import_work_tree "data/Структура ЕР.xlsx" --clear
```

После этого админка будет доступна по `/admin/`.

## Как открыть проект пользователям

### Вариант 1. Без DNS, сразу по IP

Если у вас пока нет доступа к DNS, пользователи смогут заходить по адресу:

```text
http://SERVER_IP:9000
```

Для этого порт `9000` должен быть открыт на сервере и во внешнем firewall.

### Вариант 2. Через поддомен и HTTPS

Когда появится доступ к DNS, создайте A-запись:

```text
mob.s-nk.su -> SERVER_IP
```

После этого:

- в `.env.production` укажите `DJANGO_ALLOWED_HOSTS=mob.s-nk.su`
- укажите `DJANGO_CSRF_TRUSTED_ORIGINS=https://mob.s-nk.su`
- оставьте `APP_DOMAIN=mob.s-nk.su`
- перезапустите контейнеры

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Traefik возьмет сертификат Let's Encrypt, если домен уже указывает на сервер и его конфигурация на хосте это разрешает.

## Полезные команды

```bash
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml restart
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml exec db psql -U s_nk_mob -d s_nk_mob
```
