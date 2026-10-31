# Материалы заключительного аудита

- [`FINAL_AUDIT_REPORT.md`](FINAL_AUDIT_REPORT.md) — техническое заключение, замечания и матрица приёмки.
- [`FINAL_SUBMISSION_INDEX.md`](FINAL_SUBMISSION_INDEX.md) — восемь точных файлов для сдачи и их SHA-256.
- [`results.json`](results.json) — 55 структурированных проверок с методом, ожиданием, фактом, статусом и свидетельством.
- [`protocol.json`](protocol.json) — сокращённый обезличенный протокол скачанных Releases, архивов и запусков.
- [`experiment_recalculation.json`](experiment_recalculation.json) — независимый пересчёт трёх корпусов из исходных CSV; [`historical_preservation.json`](historical_preservation.json) — сохранность 21 и 118 исторических файлов.
- [`report_inspection.json`](report_inspection.json), [`tag_sync.json`](tag_sync.json), [`security_scan.json`](security_scan.json), [`smoke_log.json`](smoke_log.json), [`offline_lab4.json`](offline_lab4.json), [`integrated_main.json`](integrated_main.json) — адресные свидетельства.

Сценарии в этой директории повторяют проверки, не меняя опубликованные версии. Целевая среда — Windows 11 / Python 3.14; требуется авторизованный GitHub CLI для приватных Releases. Сначала скачать вложения четырёх тегов в `run_output/final_audit_downloads/<tag>/`. Затем запустить `collect_evidence.py`, `smoke_archives.py`, `recompute_experiments.py`, `verify_tag_sync.py`, `inspect_reports.py`, `security_scan.py`, `build_results.py` в указанном порядке. Скрипты не делают платных вызовов и пишут новые эксперименты только в отдельный `run_output` распакованных копий. Сырой протокол содержит временные локальные пути и остаётся в игнорируемом `run_output/final_audit_execution_raw.json`; публикуемый `protocol.json` обезличен.

Отдельная проверка полной автономности ЛР №4 запускается `py -3.14 tools/audit_lab4_archive.py` из корня проекта. Она создаёт чистую временную виртуальную среду, устанавливает пакет из `vendor/wheels/` с `--no-index` и пишет детальный локальный протокол в `run_output/lab4_v1_1_archive_reproduction.json`. Краткий результат этого аудита сохранён в `offline_lab4.json`.
