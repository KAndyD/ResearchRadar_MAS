# ResearchRadar MAS

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

Релиз: [lab1-v1.2](https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.2). Известные ограничения и подтверждённые испытания: [состояние тестов](docs/test-status.md). Архивы сдачи и полного аудита доступны в Release; `tools/package_submission.py` собирает их локально из зафиксированной версии. Лабораторные работы №2–4 не реализованы.
