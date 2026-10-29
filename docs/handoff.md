# Передача состояния проекта

1. Прочитать `AGENTS.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/progress.md`, `docs/test-status.md` и проверить `git status`.
2. Запустить `py -3.14 -m unittest discover -s tests -v` и автономный CLI DEMO.
3. Основной отчёт — `deliverables/ResearchRadar_MAS_Architecture.docx` и `.pdf`. Он не содержит учебных организационных формулировок. Учебная сверка — `submission_manifest.md`.
4. Схемы — редактируемые `docs/diagrams/*.svg`, в DOCX встроены SVG-объекты, PDF использует векторные элементы. PDF строится из того же текста через `tools/build_report.py` и `tools/build_pdf.py`; SVG в DOCX встраивает `tools/embed_vectors.ps1`. Для авторского PDF нужен пакет `svglib` из `tools/requirements-report.txt`.
5. Ключ OpenRouter и SQLite-журнал находятся вне Git в `%LOCALAPPDATA%/ResearchRadar_MAS`. Исторический расход одного раннего вызова неизвестен; новый журнал сохраняет записи до отправки.
6. GDELT в текущей среде вернул 429. Google News RSS проверен отдельно. Не смешивать эти статусы.
7. Тег и Release `lab1-v1.1` опубликованы: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.1. Релизный коммит `1628989`, GitHub Actions run `40975152654` успешен. Старый `lab1-v1.0` не трогать. GitHub CLI: `C:/Program Files/GitHub CLI/gh.exe`.
8. Не начинать лабораторную №2 без отдельного поручения. Её ближайшая инженерная тема — сравнение политик распределения задач на одинаковых сценариях.
