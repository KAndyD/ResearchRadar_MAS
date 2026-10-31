# ResearchRadar MAS — комплект лабораторной №4

Автор: Коротаев Андрей Дмитриевич, Б24-507. Версия: `lab4-v1.0`.

Основной самостоятельный отчёт: `deliverables/ResearchRadar_MAS_Reliability_Assessment.pdf`; редактируемая версия — `.docx`. Векторные первоисточники двух схем: `deliverables/figures/*.svg`.

Реализация: `src/researchradar/coordination.py`, `evidence_analysis.py`, `llm.py`, `cli_stage4.py`. Неблагоприятные воздействия и полный парный эксперимент: `tools/lab4_probe.py`, `tools/run_lab4_experiments.py`, `experiments/lab4/scenarios.json`, `experiments/lab4/results/`. Независимая проверка данных: `tools/verify_lab4_results.py`.

Исторический контроль — точный архив кода тега `lab3-v1.1`, SHA-256 `da223cc3ff29e0a0842c159270c4697ca3d5960d0359e6388119de8f56caaa2a`. Корпус: 10 сценариев × 5 seed × 2 варианта = 100 трасс. Результат: нарушения политики 25/50 → 0/50, корректные исходы 25/50 → 50/50. Наблюдения ограничены данным корпусом.

Контур Qwen: авторские имитации ответов и их проверки — `experiments/lab4/llm_results/`; отдельно один реальный вызов и его отклонённый ответ — `experiments/lab4/live_qwen_evidence.json`. Реальная генерация стоила `$0.00042185`; сохранённый ответ отклонён за неточную цитату. Имитации не являются ответами модели. `tools/verify_lab4_llm_results.py` перепроверяет обе записи.

Руководство по автономному воспроизведению: `docs/lab4_reproduction.md`. Модель угроз: `docs/lab4_threat_model.md`. ZIP сдачи содержит исходники, данные, отчёт и DOCX; аудиторский ZIP дополнительно содержит методичку и свидетельства. Оба ZIP содержат контрольные суммы членов.
