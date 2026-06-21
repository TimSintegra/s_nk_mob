# Деплой s-nk-mob

Короткая памятка, как обновлять проект на сервере.

## Что должно быть на сервере

- установлен Docker
- установлен `docker-compose` 1.29.2 или новый `docker compose`
- доступ к репозиторию GitHub
- файл `.env.production` рядом с `docker-compose.prod.yml`

## Важное про `git pull`

GitHub больше не принимает пароль аккаунта для HTTPS-операций.

Когда `git pull` спросит:

- `Username` - вводишь свой GitHub username
- `Password` - вставляешь Personal Access Token, а не обычный пароль

Токен у тебя уже сохранён в избранных в Telegram, так что просто вставляешь его вместо пароля.

## Первый деплой на сервере

Если проект ещё не развернут:

```bash
cd /var/www
git clone https://github.com/TimSintegra/s_nk_mob.git
cd s_nk_mob
cp .env.production.example .env.production
nano .env.production
docker-compose -f docker-compose.prod.yml up -d --build
```

Проверка:

```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs --tail=120 web
```

## Обычное обновление

Если проект уже развернут и нужно просто обновить код:

```bash
cd /path/to/s-nk-mob
git pull
docker-compose -f docker-compose.prod.yml build web
docker rm -f s_nk_mob_web
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml up -d --no-deps web
docker-compose -f docker-compose.prod.yml exec web uv run python manage.py import_work_tree "data/Структура ЕР.xlsx" --clear
docker-compose -f docker-compose.prod.yml ps
```

> **Важно:** теперь скрипт обрабатывает **все листы** файла Excel.
> Каждый лист становится отдельным корневым разделом на главной странице.
> Структура на каждом листе: строка 1 (розовый) → корень, строка 2 (синий) → подразделы,
> строка 3 (зелёный) → подразделы второго уровня, строки 4+ (белые) → работы.

## Если `git pull` не проходит

Иногда на сервере могут остаться локальные правки. Тогда сначала сохрани их:

```bash
git status
git stash push -m "server local changes"
git pull
```

Если нужно вернуть спрятанные изменения:

```bash
git stash pop
```

## Если при запуске `web` появляется `ContainerConfig`

Это баг старого `docker-compose 1.29.2`. В этом случае не трогай volume с PostgreSQL и сделай так:

```bash
docker ps -a --filter name=s_nk_mob
docker rm -f s_nk_mob_web
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml up -d --no-deps web
```

Если контейнер был пересоздан, после этого снова запускай импорт:

```bash
docker-compose -f docker-compose.prod.yml exec web uv run python manage.py import_work_tree "data/Структура ЕР.xlsx" --clear
```

## Если Excel не виден внутри контейнера

Проверь, что файл реально попал в образ:

```bash
docker-compose -f docker-compose.prod.yml exec web sh -lc 'ls -la /app/data'
```

Если папки или файла нет, значит образ надо пересобрать:

```bash
docker-compose -f docker-compose.prod.yml build web
docker rm -f s_nk_mob_web
docker-compose -f docker-compose.prod.yml up -d --no-deps web
```

## Проверка после деплоя

```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs --tail=120 web
curl -I http://127.0.0.1:9000/login/
```

Если сайт работает через домен, можно ещё проверить:

```bash
curl -vkI https://mob.s-nk.su/login/
```

## Что нельзя делать

- не выполняй `docker-compose down -v`
- не удаляй volume `postgres_data`
- не вводи обычный пароль GitHub вместо token

## Частые полезные команды

```bash
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs --tail=120 web
docker-compose -f docker-compose.prod.yml restart web
docker ps -a --filter name=s_nk_mob
docker volume ls | grep postgres
```
