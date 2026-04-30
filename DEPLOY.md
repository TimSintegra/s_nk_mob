# Деплой s-nk-mob

Памятка для обновления приложения на сервере.

## Обычный деплой

```bash
cd /path/to/s-nk-mob
git pull
git log --oneline -1
docker-compose -f docker-compose.prod.yml up -d --build
docker-compose -f docker-compose.prod.yml ps
```

Если на сервере установлен новый compose-плагин, можно использовать:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

На текущем сервере используется старый `docker-compose 1.29.2`, поэтому рабочая команда:

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

## Если появилась ошибка ContainerConfig

Старый `docker-compose 1.29.2` иногда падает с ошибкой:

```text
KeyError: 'ContainerConfig'
```

В этом случае не удаляй volume с базой. Нельзя выполнять:

```bash
docker-compose -f docker-compose.prod.yml down -v
```

Безопасный порядок:

```bash
docker ps -a --filter name=s_nk_mob
docker rm -f ИМЯ_ИЛИ_ID_СТАРОГО_WEB_КОНТЕЙНЕРА
docker rm -f ИМЯ_ИЛИ_ID_СТАРОГО_DB_КОНТЕЙНЕРА
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml up -d --no-deps web
docker-compose -f docker-compose.prod.yml ps
```

Если контейнеры были переименованы compose-ом, их имена могут выглядеть так:

```text
f9df80971b91_s_nk_mob_web
66f5a6b5247f_s_nk_mob_db
```

Удалять такие контейнеры можно. Данные Postgres хранятся в named volume `postgres_data`, его не трогаем.

## Проверка приложения

```bash
docker-compose -f docker-compose.prod.yml logs --tail=120 web
curl -I http://127.0.0.1:9000/login/
```

Если приложение работает напрямую, `curl` вернет ответ от `gunicorn`. При включенном HTTPS-редиректе может быть:

```text
HTTP/1.1 301 Moved Permanently
Location: https://127.0.0.1:9000/login/
```

Это нормально для прямой проверки HTTP-порта.

## Проверка Traefik

Если сайт через домен показывает `Gateway Timeout`, проверь, куда Traefik направляет трафик:

```bash
docker logs --tail=120 proxy-server | grep s-nk-mob
docker inspect s_nk_mob_web --format '{{json .NetworkSettings.Networks}}'
docker inspect proxy-server --format '{{json .NetworkSettings.Networks}}'
```

В логах Traefik для `s-nk-mob` должен быть адрес из сети `docker_proxy-server-net`, например:

```text
Creating server 0 http://172.19.0.2:8000
```

Если Traefik выбрал адрес из другой сети, например `192.168.0.3:8000`, проверь label в `docker-compose.prod.yml`:

```yaml
- "traefik.docker.network=${TRAEFIK_NETWORK:-docker_proxy-server-net}"
```

После исправления пересоздай web-контейнер:

```bash
docker ps -a --filter name=s_nk_mob_web
docker rm -f ИМЯ_ИЛИ_ID_WEB_КОНТЕЙНЕРА
docker-compose -f docker-compose.prod.yml up -d --no-deps web
docker restart proxy-server
docker logs --tail=120 proxy-server | grep s-nk-mob
```

## Полезные команды

```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs --tail=120 web
docker-compose -f docker-compose.prod.yml restart web
docker ps -a --filter name=s_nk_mob
docker volume ls | grep postgres
```
