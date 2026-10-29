# ResearchRadar MAS

Программный фундамент и материалы лабораторной работы №1 по курсу «Теория многоагентных систем». Главный нормативный документ: [методичка](project_guide/Лабораторные-МАС.pdf). Архитектура описана в [спецификации](docs/architecture.md).

## Windows 11 и Python 3.14

```powershell
py -3.14 -m pip install -e .
py -3.14 -m unittest discover -s tests -v
py -3.14 -m researchradar.cli "multi agent systems" --mode demo
py -3.14 -m researchradar.cli "multi agent systems" --mode live
```

Выход `run_output/result.json` содержит список источников, состояния агентов и трассу сообщений. DEMO полностью автономен и явно помечает синтетические записи. LIVE использует OpenAlex и GDELT; доступность зависит от сети и провайдеров. Платных LLM-вызовов эти команды не делают. Отдельный клиент OpenRouter находится в `src/researchradar/llm.py`; ключ читается только из локальной конфигурации вне репозитория.

Отчёт и схемы лежат в `deliverables/` и `docs/diagrams/`. ЛР №2–4 пока не реализованы.
