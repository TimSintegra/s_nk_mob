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

## Если домен отвечает 404, а Traefik работает

Если `https://mob.s-nk.su/` отвечает `404`, но в логах `proxy-server` нет ошибок Docker provider, проверь состояние контейнеров проекта:

```bash
docker ps -a --filter name=s_nk_mob
docker-compose -f docker-compose.prod.yml ps
docker logs --tail=120 s_nk_mob_web
docker logs --tail=80 s_nk_mob_db
```

Если `web` пишет `failed to resolve host 'db'`, а `docker-compose up -d` падает с ошибкой вида:

```text
network ... not found
```

значит у проекта пропала внутренняя сеть `s-nk-mob_default`, а старые контейнеры остались привязаны к несуществующему network ID. В этом случае не трогай volume с базой и не выполняй:

```bash
docker-compose -f docker-compose.prod.yml down -v
```

Безопасный порядок восстановления:

```bash
docker ps -a --filter name=s_nk_mob
docker rm -f s_nk_mob_web
docker rm -f s_nk_mob_db
docker network ls | grep s-nk-mob
docker network rm s-nk-mob_default
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml up -d --no-deps web
docker-compose -f docker-compose.prod.yml ps
```

Если `docker network rm s-nk-mob_default` ответит, что сети нет, это нормально. После пересоздания контейнеров Compose создаст сеть заново.

Проверка после восстановления:

```bash
docker logs --tail=80 s_nk_mob_db
docker logs --tail=120 s_nk_mob_web
curl -I http://127.0.0.1:9000/login/
curl -vkI https://mob.s-nk.su/login/
```

Нормальный результат:

```text
HTTP/1.1 301 Moved Permanently
Location: https://127.0.0.1:9000/login/
```

и снаружи:

```text
HTTP/2 200
```

## Полезные команды

```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs --tail=120 web
docker-compose -f docker-compose.prod.yml restart web
docker ps -a --filter name=s_nk_mob
docker volume ls | grep postgres
```

## Быстрый деплой после `git pull`

Если ты уже на сервере и нужно просто обновить проект, делай так:

```bash
cd /path/to/s-nk-mob
git pull
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec web uv run python manage.py import_work_tree "data/Структура ЕР.xlsx" --clear
docker-compose -f docker-compose.prod.yml ps
```

Если `docker-compose -f docker-compose.prod.yml up -d --build` падает с `ContainerConfig`, это известная проблема `docker-compose 1.29.2`. Тогда используй обходной путь:

```bash
docker ps -a --filter name=s_nk_mob
docker rm -f s_nk_mob_web
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml up -d --no-deps web
docker-compose -f docker-compose.prod.yml exec web uv run python manage.py import_work_tree "data/Структура ЕР.xlsx" --clear
```

Если нужно именно пересобрать образ, а не только перезапустить контейнер, можно сделать так:

```bash
docker-compose -f docker-compose.prod.yml build web
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml up -d --no-deps web
```

Важно:
- не делай `docker-compose down -v`, чтобы не удалить volume с PostgreSQL;
- перед импортом можно сделать дамп базы;
- `--clear` не удаляет записи физически, а скрывает устаревшие узлы.
