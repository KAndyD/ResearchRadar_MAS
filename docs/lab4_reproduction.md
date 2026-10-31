# Воспроизведение исследования устойчивости

## Среда

Windows 11, Python 3.14. Код работает без Docker, Git, сети и OpenRouter. Из архива устанавливаются зависимости `pyproject.toml`; для автономной проверки допустим локальный Python с уже установленными `requests` и `pytest`/`unittest`. Ключ API не нужен.

## Исторический контроль

`experiments/lab4/baseline_lab3_v1.1.zip` получен из опубликованного тега `lab3-v1.1` командой `git archive`, без изменения исходников. Его SHA-256 — `da223cc3ff29e0a0842c159270c4697ca3d5960d0359e6388119de8f56caaa2a`. Стенд импортирует модуль из ZIP через `PYTHONPATH` и проверяет путь загрузки в каждом запуске. Для защищённого варианта используется исходный код из распакованной копии. `protected_code_commit` зафиксирован в `experiments/lab4/results/metadata.json`.

## Команды

```powershell
py -3.14 -m unittest discover -s tests -v
py -3.14 -m researchradar.cli_stage4 'multi agent systems' --mode demo --analysis recorded --recorded-analysis data/lab4_fixture_analysis.json --output run_output/lab4_demo.json
py -3.14 tools/run_lab4_experiments.py --repeats 5 --output run_output/lab4_replay
py -3.14 tools/verify_lab4_results.py run_output/lab4_replay
py -3.14 tools/run_lab4_llm_experiments.py --output run_output/lab4_llm_replay
py -3.14 tools/verify_lab4_llm_results.py run_output/lab4_llm_replay
```

Новые результаты записываются в `run_output/`; утверждённые корпуса в `experiments/lab4/results/` и `experiments/lab4/llm_results/` не перезаписываются. В распакованной копии `protected_code_commit` может быть `null` с причиной `unavailable_no_git_metadata`; этот статус честно описывает отсутствие `.git` и не влияет на результаты. Проверяется также импорт исходников из копии.

## Определения метрик

`policy_violation` означает воспроизведённое принятие подмены, падение из-за malformed result, неразрешённый shutdown, победу отрицательной ставки или запрещённую операцию. `correct_outcome` дополнительно требует ожидаемого числа завершённых задач и отсутствия ошибок (кроме честного частичного результата при HTTP 429). `wall_ms` включает старт процесса. Сценарии, точные правила и сырые значения находятся в `scenarios.json`, `tools/run_lab4_experiments.py`, `raw.csv` и трассах. Восемь имитаций ответов LLM — авторские данные, не генерации Qwen; исторического аналога этой функции в `lab3-v1.1` нет.

## Реальный вызов модели

`experiments/lab4/live_qwen_evidence.json` содержит контекст, сохранённый ответ Qwen, результат повторной детерминированной проверки и подтверждённую стоимость одного вызова. Модель составила цитату из двух отдельных фрагментов аннотации; валидатор отказал с `ungrounded_scientific_evidence`. Сама текстовая генерация без API не повторяется, но проверка сохранённого ответа повторяется `tools/verify_lab4_llm_results.py`. Одного вызова недостаточно для оценки вероятности prompt injection.

## Проверка архивов

В каждом ZIP файл `ARCHIVE_MANIFEST.txt` перечисляет SHA-256 членов. Проверяющий распаковывает архив вне дерева Git, сверяет SHA-256 и запускает команды выше. `project_guide/Лабораторные-МАС.pdf` и дополнительные аудитные свидетельства находятся в аудиторском архиве.
