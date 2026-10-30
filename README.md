# ResearchRadar MAS

**Текущая версия: лабораторная №2, `lab2-v1.1`.** ResearchRadar MAS распределяет поиск научных публикаций и новостей между шестью автономными исполнителями. Реализованы централизованное назначение и Contract Net. [Отчёт PDF](deliverables/ResearchRadar_MAS_Task_Allocation.pdf), [DOCX](deliverables/ResearchRadar_MAS_Task_Allocation.docx), [сверка требований](submission_manifest_lab2.md). Принятая версия первой работы `lab1-v1.2` сохранена.

## Версия 2: быстрый запуск

```powershell
py -3.14 -m pip install -e .
py -3.14 -m unittest discover -s tests -q
py -3.14 -m researchradar.cli_stage2 "multi agent systems" --mode demo --coordination centralized
py -3.14 -m researchradar.cli_stage2 "multi agent systems" --mode demo --coordination contract-net
py -3.14 tools/run_experiments.py --repeats 12 --output run_output/experiments
```

DEMO и эксперименты используют явно синтетический фиксированный набор `data/frozen_sources.json` без сети и платных API. Результат и трасса DEMO сохраняются в `run_output/stage2-result.json`. Опубликованные 96 измерений находятся в `experiments/results/`. Новый запуск по умолчанию пишет в `run_output/experiments/`, сохраняя исходный корпус; `--output` меняет этот путь. Там создаются `raw.csv`, `summary.json`, `paired.json`, `metadata.json`, трассы и SVG-графики. Параметры нагрузки для пары механизмов одинаковы; измеренное время также зависит от планировщика ОС.

## Запуск из распакованного архива без Git

Распакуйте `ResearchRadar_MAS_lab2_v1.1_audit.zip` в отдельный каталог вне другого Git-репозитория. Из этого каталога в PowerShell:

```powershell
py -3.14 -m pip install -e .
py -3.14 -m unittest discover -s tests -q
py -3.14 tools/run_experiments.py --repeats 1 --output run_output/experiment_smoke
```

Git не требуется для исследования. Скрипт берёт версию из собственного константного поля; достоверный SHA записывает только при доступном Git-репозитории именно в корне этой копии. В архиве поле `code_commit_at_run` нового прогона будет `null`, а `code_commit_source` объяснит отсутствие метаданных Git. Первоначальные 96 измерений были получены на коммите `2e38714e768e044928208e89009fe74cf7da9f87`; более поздний SHA выпуска обозначает сборку и не заменяет происхождение измерений. Одно повторение создаёт восемь запусков и служит проверкой работоспособности, а не заменой опубликованного корпуса.

LIVE: `py -3.14 -m researchradar.cli_stage2 "multi agent systems" --mode live --coordination contract-net --news-source rss --news-window-days 30`. Адаптеры OpenAlex, Crossref, arXiv и Google News RSS проверены в LIVE. `--news-window-days` добавляет к RSS-запросу `when:Nd`, но не гарантирует строгой фильтрации дат. GDELT доступен через `--news-source gdelt`; последняя проверка дала HTTP 429. Отказ отдельного источника сохраняет частичные результаты остальных.

Qwen необязательна. `--llm recorded --recorded-plan data/recorded_plan.json` воспроизводит сохранённый альтернативный поисковый запрос без оплаты для той же темы. `--llm live` требует LIVE-режима, ключ вне Git и проверенные тарифы `--input-rate` и `--output-rate` в USD за миллион токенов. Модель формирует альтернативный запрос для дополнительной научной задачи; ответ валидируется. Бюджет клиента — 8 USD, оценочный предел вызова — 0,05 USD, журнал затрат хранится вне Git. Обычный запуск, тесты и эксперименты не обращаются к Qwen.

Новые компоненты: `src/researchradar/coordination.py` (очереди, агенты, механизмы), `scientific.py` (Crossref и arXiv), `planning.py` (Qwen), `tools/run_experiments.py` (парные испытания). Статусы источников и затраты: `docs/source_policy.md`, `docs/api_validation.md`. Отчёт пересобирают `tools/build_lab2_report.py`, затем `tools/build_lab2_pdf.py`, затем `tools/embed_lab2_vectors.ps1`; PDF строится до встраивания SVG в DOCX. Архивы формирует `tools/package_lab2.py`. Старый интерфейс `python -m researchradar.cli` оставлен для первой версии.

## Архив первой версии

ResearchRadar MAS собирает научные публикации и новости по одной теме с помощью четырёх программных агентов. Код, схемы и самостоятельный [архитектурный отчёт](deliverables/ResearchRadar_MAS_Architecture.pdf) подготовлены для курса «Теория многоагентных систем». Учебная сверка вынесена в [сопроводительный документ](submission_manifest.md).

## Установка и запуск на Windows 11

Требуется Python 3.14. В PowerShell из корня репозитория:

```powershell
py -3.14 -m pip install -e .
py -3.14 -m unittest discover -s tests -v
py -3.14 -m researchradar.cli "multi agent systems" --mode demo
py -3.14 -m researchradar.cli "artificial intelligence" --mode live --news-source rss
```

`demo` работает без сети и платных API. `live` по умолчанию использует OpenAlex и GDELT; `--news-source rss` явно выбирает резервный Google News RSS. GDELT может ответить HTTP 429; его успех нельзя выводить из успешной работы RSS. Результат записывается в `run_output/result.json`, включая `request`, `tasks`, `materials`, `errors`, `agents` и `trace`. Путь меняется аргументом `--output`.

Публикации сохраняют DOI и аннотацию при наличии; новости содержат заголовок, URL и дату. DEMO-записи помечены `synthetic_fixture`. Сводка не делает выводов по полному тексту и не подтверждает связи между источниками.

## Компоненты

- `src/researchradar/engine.py`: координатор, поисковые агенты, синтезатор, очереди и маршрутизатор.
- `src/researchradar/sources.py`: OpenAlex, GDELT, Google News RSS и автономные fixtures.
- `src/researchradar/llm.py`: отдельный бюджетируемый клиент Qwen через OpenRouter с постоянным журналом SQLite.
- `docs/architecture.md`: подробная техническая спецификация.
- `docs/diagrams/*.svg`: редактируемые векторные схемы.
- `docs/source_policy.md`: статусы источников и границы доверия.
- `docs/api_validation.md`: результаты LIVE-проверок и учёт расходов.

Обычный запуск и тесты не обращаются к OpenRouter. Ключ читается из `%LOCALAPPDATA%\ResearchRadar_MAS\.env` или переменной окружения; журнал затрат хранится вне репозитория в `%LOCALAPPDATA%\ResearchRadar_MAS\usage.sqlite3`. Основной бюджет проекта — 10 USD, внешний лимит отдельного ключа около 8 USD, резерв 2 USD. Клиент по умолчанию ограничивает локальный расход 8 USD и оценочную стоимость вызова 0,05 USD; тарифы входных и выходных токенов передаются явно после проверки актуальной цены модели.

## Отчёт и выпуск

Отчёт генерируется `tools/build_report.py`; PDF строится из того же текста скриптом `tools/build_pdf.py`, а SVG встраиваются в DOCX через `tools/embed_vectors.ps1` и Microsoft Word. Для самостоятельной пересборки на Windows нужны пакеты из `tools/requirements-report.txt` и установленный Word. Сначала запустить `build_report.py`, затем `build_pdf.py`, затем `embed_vectors.ps1`; PDF надо строить до встраивания SVG в DOCX, пока в нём есть текстовые маркеры рисунков. Оба итоговых файла проверяются визуально. Исходники, тесты, DOCX, PDF, SVG и сопроводительный документ входят в локальный архив сдачи.

Релиз: [lab1-v1.2](https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.2). Исторические проверки: [состояние тестов](docs/test-status.md). Архивы первой работы доступны в Release; `tools/package_submission.py` собирает их локально из зафиксированной версии.
