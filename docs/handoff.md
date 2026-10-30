# Передача состояния проекта

1. Прочитать `AGENTS.md`, `project_guide/Лабораторные-МАС.pdf`, `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, `docs/test-status.md`, `docs/source_policy.md`, `docs/api_validation.md`; проверить `git status`.
2. Запуск без сети и оплаты: `py -3.14 -m pip install -e .`, `py -3.14 -m unittest discover -s tests -v`, `py -3.14 -m researchradar.cli "multi agent systems" --mode demo`. Очищенные результаты — `audit_evidence/`.
3. Основной отчёт: `deliverables/ResearchRadar_MAS_Architecture.docx` и `.pdf`; учебная сверка — `submission_manifest.md`. Схемы — `docs/diagrams/*.svg`. Пересборка: `tools/build_report.py`, затем `tools/build_pdf.py`, затем `tools/embed_vectors.ps1`; PDF строится до замены текстовых якорей на SVG в DOCX.
4. Архивы `ResearchRadar_MAS_lab1_v1.2_submission.zip` и `ResearchRadar_MAS_lab1_v1.2_audit.zip` создаёт `tools/package_submission.py`. Внутри каждого — `ARCHIVE_MANIFEST.txt` с commit SHA и SHA-256 членов; аудиторский архив дополнительно содержит очищенные свидетельства тестов и DEMO. ZIP публикуются как Release assets и не отслеживаются Git.
5. Ключ OpenRouter и SQLite-журнал находятся вне Git в `%LOCALAPPDATA%/ResearchRadar_MAS`. Последний Qwen-вызов был отдельным платным smoke test; повторять его без необходимости не надо. Исторический общий расход неизвестен.
6. GDELT вернул 429, резервный Google News RSS работал отдельно. Crossref и arXiv — только проектные источники без адаптеров. Не смешивать статусы.
7. Тег и Release `lab1-v1.2`: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.2. Старые выпуски не переписывать. GitHub CLI: `C:/Program Files/GitHub CLI/gh.exe`.
8. Лабораторную №2 не начинать без отдельного поручения. Ближайший архитектурный риск для неё — централизованный координатор и отсутствие конкурентных переговоров между кандидатами; реестр компетенций допускает несколько исполнителей одной подзадачи, но текущая политика выбирает первого доступного.
