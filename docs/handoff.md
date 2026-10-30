# Передача состояния проекта

## Исправленная версия: lab2-v1.1

Главная корректировка: `tools/run_experiments.py` больше не требует Git; SHA нового запуска записывается только для чистого checkout с `.git` в корне копии, иначе ставятся `null` и причина. Скрипт по умолчанию пишет в `run_output/experiments`, сохраняя исходные 96 измерений. `docs/experiment_provenance.md` разъясняет различие исходного коммита измерений `2e38714` и более позднего релизного коммита. Отчёт, алгоритмы распределения и научные данные не менялись.

Для независимой проверки распаковать `ResearchRadar_MAS_lab2_v1.1_audit.zip` **вне любого Git-репозитория**. На Windows/Python 3.14 запустить `py -3.14 -m pip install -e .`, `py -3.14 -m unittest discover -s tests -q`, `py -3.14 tools/run_experiments.py --repeats 1 --output run_output/experiment_smoke`. Ожидаются 35 тестов, восемь строк CSV, четыре сценария, два механизма, `code_commit_at_run: null`, `code_commit_source: unavailable_no_git_metadata`. Интеграционный тест также создаёт отдельную копию вне Git и убирает Git из PATH. Сравнение абсолютных миллисекунд между машинами не требуется.

Сборка ZIP: `py -3.14 tools/package_lab2.py` после финального коммита. Упаковщик создаёт `ResearchRadar_MAS_lab2_v1.1_submission.zip` и `ResearchRadar_MAS_lab2_v1.1_audit.zip`, включает старый корпус, новые тесты и описание происхождения, записывает SHA-256 каждого члена и отдельно SHA архивного кода и первоначального измерения. Кандидат ZIP коммита `32edad6` проверен вне Git: 35 тестов и восемь запусков; свидетельство в `audit_evidence/lab2_v1.1_reproduction.json`. Старые выпуски `lab1-v1.2` и `lab2-v1.0` сохранены.

## История: lab2-v1.0

1. Прочитать `AGENTS.md`, оригинальную методичку `project_guide/Лабораторные-МАС.pdf`, `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, `docs/test-status.md`, `docs/source_policy.md`, `docs/api_validation.md` и `submission_manifest_lab2.md`. Методичка имеет приоритет; лекций в проекте нет.
2. На Windows/Python 3.14: `py -3.14 -m pip install -e .`, `py -3.14 -m unittest discover -s tests -q`. Запуск: `py -3.14 -m researchradar.cli_stage2 "multi agent systems" --mode demo --coordination contract-net` или `--coordination centralized`. Оба DEMO полностью автономны; `run_output/` игнорируется Git.
3. Эксперимент: `py -3.14 tools/run_experiments.py --repeats 12`. `data/frozen_sources.json` — явно синтетический набор; `experiments/results/raw.csv`, `summary.json`, `paired.json`, `metadata.json`, `traces/` и `*.svg` — проверяемые результаты. Условия seed парные, но миллисекунды могут измениться из-за ОС. Координационное время суммируется по задачам и может перекрываться.
4. LIVE: `py -3.14 -m researchradar.cli_stage2 "multi agent systems" --mode live --coordination contract-net --news-source rss`. Qwen не обязательна: режим `recorded` использует `data/recorded_plan.json` для соответствующего вопроса, режим `live` требует явно проверенные тарифы и ключ вне репозитория. Не повторять платный smoke test без необходимости. Известные расходы и статус источников — `docs/api_validation.md`.
5. Отчёт: `deliverables/ResearchRadar_MAS_Task_Allocation.docx/.pdf`; пересборка в порядке `tools/build_lab2_report.py`, `tools/build_lab2_pdf.py`, `tools/embed_lab2_vectors.ps1` с зависимостями `tools/requirements-report.txt` и Word. Схемы `docs/diagrams/lab2_*.svg`, графики `experiments/results/*.svg`.
6. Архивы `ResearchRadar_MAS_lab2_v1.0_submission.zip` и `_audit.zip` создаёт `tools/package_lab2.py` после Git-коммита; внутри `ARCHIVE_MANIFEST.txt` с SHA-256. Аудиторский архив включает DOCX и безопасные результаты проверок. Раздельная первая версия `lab1-v1.2` и её релиз не переписываются.
7. Перспектива ЛР №3: сообщения CFP/proposal/accept уже явные, но будущий протокол переговоров должен самостоятельно определить полезность, резервирование ресурсов, конфликт нескольких параллельных контрактов и строгие границы сроков. ЛР №3–4 не начинать без нового поручения.

## Архив передачи первой версии

1. Прочитать `AGENTS.md`, `project_guide/Лабораторные-МАС.pdf`, `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, `docs/test-status.md`, `docs/source_policy.md`, `docs/api_validation.md`; проверить `git status`.
2. Запуск без сети и оплаты: `py -3.14 -m pip install -e .`, `py -3.14 -m unittest discover -s tests -v`, `py -3.14 -m researchradar.cli "multi agent systems" --mode demo`. Очищенные результаты — `audit_evidence/`.
3. Основной отчёт: `deliverables/ResearchRadar_MAS_Architecture.docx` и `.pdf`; учебная сверка — `submission_manifest.md`. Схемы — `docs/diagrams/*.svg`. Пересборка: `tools/build_report.py`, затем `tools/build_pdf.py`, затем `tools/embed_vectors.ps1`; PDF строится до замены текстовых якорей на SVG в DOCX.
4. Архивы `ResearchRadar_MAS_lab1_v1.2_submission.zip` и `ResearchRadar_MAS_lab1_v1.2_audit.zip` создаёт `tools/package_submission.py`. Внутри каждого — `ARCHIVE_MANIFEST.txt` с commit SHA и SHA-256 членов; аудиторский архив дополнительно содержит очищенные свидетельства тестов и DEMO. ZIP публикуются как Release assets и не отслеживаются Git.
5. Ключ OpenRouter и SQLite-журнал находятся вне Git в `%LOCALAPPDATA%/ResearchRadar_MAS`. Последний Qwen-вызов был отдельным платным smoke test; повторять его без необходимости не надо. Исторический общий расход неизвестен.
6. GDELT вернул 429, резервный Google News RSS работал отдельно. Crossref и arXiv — только проектные источники без адаптеров. Не смешивать статусы.
7. Тег и Release `lab1-v1.2`: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.2. Старые выпуски не переписывать. GitHub CLI: `C:/Program Files/GitHub CLI/gh.exe`.
8. Лабораторную №2 не начинать без отдельного поручения. Ближайший архитектурный риск для неё — централизованный координатор и отсутствие конкурентных переговоров между кандидатами; реестр компетенций допускает несколько исполнителей одной подзадачи, но текущая политика выбирает первого доступного.
