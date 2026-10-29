# Комплект сдачи лабораторной работы №1

**Дисциплина:** Теория многоагентных систем

**Автор:** Коротаев Андрей Дмитриевич, Б24-507

**Работа:** «Спецификация и архитектурное проектирование многоагентной системы»
**Версия:** `lab1-v1.1`

Основной документ — самостоятельный технический отчёт, без учебных организационных формулировок. Этот файл предназначен для сверки комплекта с методическими рекомендациями `project_guide/Лабораторные-МАС.pdf`.

| Требование методички | Материал |
| --- | --- |
| Выбор и описание прикладной задачи | Раздел 1 отчёта |
| Формальное описание МАС | Раздел 3 отчёта; `docs/architecture.md` |
| Агенты, роли, цели, знания, состояния, действия, полномочия, средства и каналы | Разделы 2–4 отчёта; `src/researchradar/engine.py`, `model.py`, `sources.py` |
| Диаграмма ролей | Рисунок 1; `docs/diagrams/roles.svg` |
| Направленный граф коммуникаций | Рисунок 2; `docs/diagrams/communication.svg` |
| Обоснование архитектуры | Разделы 2 и 7 отчёта; `docs/decisions.md` |
| Исходный код и демонстрационные материалы отдельно от отчёта | `src/`, `tests/`, `README.md`, локальный ZIP |
| Пригодность для последующих исследований | Раздел 7 отчёта; раздел «Наблюдаемость» в спецификации |

## Итоговые файлы

- `deliverables/ResearchRadar_MAS_Architecture.docx`
- `deliverables/ResearchRadar_MAS_Architecture.pdf`
- `docs/diagrams/roles.svg`, `docs/diagrams/communication.svg`
- `deliverables/ResearchRadar_MAS_lab1_v1.1_submission.zip`
- Репозиторий: https://github.com/KAndyD/ResearchRadar_MAS
- Релиз: https://github.com/KAndyD/ResearchRadar_MAS/releases/tag/lab1-v1.1

## Проверка на Windows 11

```powershell
py -3.14 -m pip install -e .
py -3.14 -m unittest discover -s tests -v
py -3.14 -m researchradar.cli "multi agent systems" --mode demo
py -3.14 -m researchradar.cli "artificial intelligence" --mode live --news-source rss
```

Результат DEMO создаётся в `run_output/result.json` и содержит трассу из шести сообщений. LIVE с GDELT запускается той же командой без `--news-source rss`. При проверке GDELT вернул HTTP 429; это ограничение внешнего сервиса, а не подтверждённый результат новостного поиска. Историческая стоимость одного раннего вызова OpenRouter не восстановлена. Подробности — `docs/test-status.md`.
