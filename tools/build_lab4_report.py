"""Build a standalone reliability report and source-backed vector figures."""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
FIG = OUT / "figures"
RESULTS = ROOT / "experiments/lab4/results"
summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
metadata = json.loads((RESULTS / "metadata.json").read_text(encoding="utf-8"))
llm = json.loads((ROOT / "experiments/lab4/llm_results/summary.json").read_text(encoding="utf-8"))
live = json.loads((ROOT / "experiments/lab4/live_qwen_evidence.json").read_text(encoding="utf-8"))
new_llm = json.loads((ROOT / "experiments/lab4_v1_1/results/summary.json").read_text(encoding="utf-8"))
live_first = json.loads((ROOT / "experiments/lab4_v1_1/live/summary.json").read_text(encoding="utf-8"))
live_second = json.loads((ROOT / "experiments/lab4_v1_1/live_round2/summary.json").read_text(encoding="utf-8"))
by = {(row["scenario"], row["variant"]): row for row in summary}
OUT.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)


def figure_files() -> None:
    names = ["normal", "wrong_run_result", "malformed_result", "source_mismatch",
             "forged_shutdown", "malicious_bid", "source_429", "wrong_correlation",
             "forbidden_delegate", "resource_owner"]
    labels = ["Норма", "Чужой run", "Ошибка формата", "Подмена типа",
              "Ложный stop", "Ставка −1", "HTTP 429", "Чужая связь",
              "Делегирование", "Чужой ресурс"]
    w, h = 1200, 700
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
           '<rect width="1200" height="700" fill="white"/>',
           '<text x="48" y="48" font-family="Arial" font-size="26" font-weight="bold">Нарушения политики в пяти повторах</text>',
           '<text x="48" y="82" font-family="Arial" font-size="16" fill="#475569">Историческая версия и защищённая версия · один сценарий на строку</text>']
    im = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(im)
    font_path = "C:/Windows/Fonts/arial.ttf"
    font = ImageFont.truetype(font_path, 21)
    small = ImageFont.truetype(font_path, 16)
    draw.text((48, 22), "Нарушения политики в пяти повторах", font=font, fill="#111827")
    draw.text((48, 59), "Историческая версия и защищённая версия · один сценарий на строку", font=small, fill="#475569")
    for i, (name, label) in enumerate(zip(names, labels)):
        y = 122 + i * 53
        bv, pv = (by[name, variant]["policy_violations"] for variant in ("baseline", "protected"))
        svg.append(f'<text x="48" y="{y+20}" font-family="Arial" font-size="17">{label}</text>')
        draw.text((48, y), label, font=small, fill="#111827")
        for value, color, offset in ((bv, "#d97706", 0), (pv, "#0f766e", 20)):
            x, yy, width = 315, y + offset, 620 * value / 5
            svg.append(f'<rect x="{x}" y="{yy}" width="{width:.1f}" height="17" rx="3" fill="{color}"/>')
            draw.rectangle((x, yy, x + max(width, 1), yy + 17), fill=color)
            svg.append(f'<text x="{x+width+10:.1f}" y="{yy+14}" font-family="Arial" font-size="15">{value}/5</text>')
            draw.text((x+width+10, yy), f"{value}/5", font=small, fill="#111827")
    svg += ['<rect x="315" y="653" width="18" height="12" fill="#d97706"/>',
            '<text x="341" y="665" font-family="Arial" font-size="15">Историческая версия</text>',
            '<rect x="510" y="653" width="18" height="12" fill="#0f766e"/>',
            '<text x="536" y="665" font-family="Arial" font-size="15">Защищённая версия</text>', '</svg>']
    draw.rectangle((315, 653, 333, 665), fill="#d97706")
    draw.text((341, 649), "Историческая версия", font=small, fill="#111827")
    draw.rectangle((510, 653, 528, 665), fill="#0f766e")
    draw.text((536, 649), "Защищённая версия", font=small, fill="#111827")
    (FIG / "policy_violations.svg").write_text("\n".join(svg), encoding="utf-8")
    im.save(FIG / "policy_violations.png")

    diagram = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="460" viewBox="0 0 1200 460">
<rect width="1200" height="460" fill="white"/>
<style>text{font-family:Arial,sans-serif;fill:#172033}.box{fill:#f0f7f7;stroke:#0f766e;stroke-width:2}.bad{fill:#fff7ed;stroke:#d97706;stroke-width:2}.line{stroke:#334155;stroke-width:2;marker-end:url(#arrow)}</style>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#334155"/></marker></defs>
<text x="40" y="45" font-size="26" font-weight="bold">Границы доверия и точки проверки</text>
<rect class="bad" x="40" y="110" width="250" height="85" rx="10"/><text x="59" y="145" font-size="18">Внешние источники</text><text x="59" y="172" font-size="15">аннотация и заголовок</text>
<rect class="box" x="395" y="110" width="260" height="85" rx="10"/><text x="415" y="145" font-size="18">Контекст с ID и scope</text><text x="415" y="172" font-size="15">данные отделены от правил</text>
<rect class="box" x="760" y="110" width="385" height="85" rx="10"/><text x="780" y="145" font-size="18">Qwen и проверка ответа</text><text x="780" y="172" font-size="15">JSON, ID, точные цитаты, категории</text>
<line class="line" x1="290" y1="152" x2="393" y2="152"/><line class="line" x1="655" y1="152" x2="758" y2="152"/>
<rect class="bad" x="40" y="295" width="250" height="85" rx="10"/><text x="59" y="330" font-size="18">Недостоверное сообщение</text><text x="59" y="357" font-size="15">run, task, correlation, bid</text>
<rect class="box" x="395" y="295" width="260" height="85" rx="10"/><text x="415" y="330" font-size="18">Шина и координатор</text><text x="415" y="357" font-size="15">допуск, валидация, повтор</text>
<rect class="box" x="760" y="295" width="385" height="85" rx="10"/><text x="780" y="330" font-size="18">Поиск и проверка ресурса</text><text x="780" y="357" font-size="15">частичный ответ при отказе источника</text>
<line class="line" x1="290" y1="337" x2="393" y2="337"/><line class="line" x1="655" y1="337" x2="758" y2="337"/>
</svg>'''
    (FIG / "trust_boundaries.svg").write_text(diagram, encoding="utf-8")
    picture = Image.new("RGB", (1200, 460), "white")
    pen = ImageDraw.Draw(picture)
    big = ImageFont.truetype(font_path, 26)
    medium = ImageFont.truetype(font_path, 18)
    pen.text((40, 25), "Границы доверия и точки проверки", font=big, fill="#172033")
    blocks = [
        (40, 110, 290, 195, "Внешние источники", "аннотация и заголовок", True),
        (395, 110, 655, 195, "Контекст с ID и scope", "данные отделены от правил", False),
        (760, 110, 1145, 195, "Qwen и проверка ответа", "JSON, ID, цитаты, категории", False),
        (40, 295, 290, 380, "Недостоверное сообщение", "run, task, correlation, bid", True),
        (395, 295, 655, 380, "Шина и координатор", "допуск, валидация, повтор", False),
        (760, 295, 1145, 380, "Поиск и проверка ресурса", "частичный ответ при отказе", False),
    ]
    for x1, y1, x2, y2, top, bottom, bad in blocks:
        pen.rounded_rectangle((x1, y1, x2, y2), radius=10,
                              fill="#fff7ed" if bad else "#f0f7f7",
                              outline="#d97706" if bad else "#0f766e", width=2)
        pen.text((x1+19, y1+26), top, font=medium, fill="#172033")
        pen.text((x1+19, y1+54), bottom, font=small, fill="#172033")
    for yy in (152, 337):
        for start, end in ((290, 395), (655, 760)):
            pen.line((start, yy, end-3, yy), fill="#334155", width=3)
            pen.polygon([(end-3, yy-7), (end+4, yy), (end-3, yy+7)], fill="#334155")
    picture.save(FIG / "trust_boundaries.png")


figure_files()
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.top_margin, sec.bottom_margin = Cm(2.1), Cm(1.9)
sec.left_margin, sec.right_margin = Cm(2.35), Cm(2.15)
normal = doc.styles["Normal"]
normal.font.name, normal.font.size = "Times New Roman", Pt(10)
normal.paragraph_format.space_after = Pt(4)
normal.paragraph_format.line_spacing = 1.08
for name, size in (("Title", 17), ("Heading 1", 13.5), ("Heading 2", 11.5)):
    style = doc.styles[name]
    style.base_style = normal
    style.font.name, style.font.size = "Times New Roman", Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_before = Pt(11)
    style.paragraph_format.space_after = Pt(5)
    style.paragraph_format.keep_with_next = True
for border in doc.styles["Title"]._element.pPr.findall(qn("w:pBdr")):
    doc.styles["Title"]._element.pPr.remove(border)


def p(text, style=None):
    return doc.add_paragraph(text, style)


def h(text):
    doc.add_heading(text, 1)


def table(headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style, t.alignment = "Table Grid", WD_TABLE_ALIGNMENT.CENTER
    for cell, value in zip(t.rows[0].cells, headers):
        cell.text = value
    for values in rows:
        for cell, value in zip(t.add_row().cells, values):
            cell.text = str(value)
    for row in t.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(8.3)


def picture(path, caption, width=15.5):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.keep_with_next = True
    para.add_run().add_picture(str(path), width=Cm(width))
    cap = p(caption)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(9)


title = p("Устойчивость многоагентной исследовательской системы к неблагоприятным воздействиям", "Title")
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
p("ResearchRadar MAS: контролируемое внедрение отказов, измерение защит и проверка доказательного анализа")
for line in ("Коротаев Андрей Дмитриевич", "Группа Б24-507", "2026"):
    pp = p(line); pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
h("Аннотация")
p("Исследована работа действующей многоагентной системы при недостоверных сообщениях, подмене результата и цели, ошибках формата, отказе внешнего источника и нарушении ресурсных полномочий. Историческая версия сравнивается с защищённой версией на одинаковых синтетических данных и seed. В десяти сценариях выполнено по пять парных повторов: 100 запусков и 100 сохранённых трасс. Защиты устранили 25 из 25 наблюдавшихся нарушений политики; корректный исход получен в 50 из 50 защищённых запусков против 25 из 50 исторических. Дополнительно разделены дословное свидетельство и непроверенная интерпретация Qwen. В шести новых реальных вызовах три первых ответа отклонены; после уточнения инструкции три ответа дали пригодную предварительную аналитику. Эти результаты относятся к заданному корпусу и не доказывают общую неуязвимость.")
h("1. Вопрос и объект исследования")
p("Как неблагоприятные воздействия меняют корректность, безопасность и доступность поиска и насколько проверки сообщений повышают устойчивость при измеримых накладных расходах? Объектом служит рабочий контур: координатор, научные и новостные агенты с очередями, Contract Net, источники, переговорная проверка и атомарный ресурсный журнал. Отдельный аналитический контур получает аннотацию научной публикации и заголовок новости и выдаёт предварительное тематическое сопоставление.")
p("Исторический контроль — точный архив принятой версии с SHA-256 " + metadata["baseline_sha256"] + ". Его импорт проверен в каждой трассе. Защищённый код зафиксирован коммитом " + str(metadata["protected_code_commit"]) + ". Исходные данные, порядок вариантов и сценарии одинаковы внутри каждой пары.")
h("2. Модель угроз и ограничения доверия")
p("Недоверенными считаются текст источника, содержимое результата поискового агента, ставка участника торгов и ответ модели. Шина проверяет допустимость маршрута и принадлежность сообщения исследованию; координатор сверяет task_id, correlation_id, отправителя, формат и семантику материала. Работник не принимает команду завершения для чужого исследования. Ресурсный журнал разрешает операции только владельцу подтверждённого резервирования. Внешний текст передаётся модели как данные; её ответ не исполняется, не запускает инструменты и допускается в вывод лишь после проверки ссылок и точных цитат.")
picture(FIG / "trust_boundaries.png", "Рисунок 1 — Точки проверки сообщений и модельного ответа", 15.2)
p("Границы остаются: строковый sender не подтверждён криптографически; участник, знающий действующие идентификаторы и представивший правдоподобный материал, может имитировать ответ. Истинность публикаций, новостей и научных утверждений не устанавливается сравнением заголовка с аннотацией. Эксперимент проверяет конкретные, явно внедрённые воздействия, а не произвольного противника.")
h("3. Методика и инструментарий")
p("Стенд внедряет воздействие в фактические интерфейсы Bus.send, Worker.score, Source.search и VerificationBudget, после чего выполняет обычный код поиска. Каждый запуск происходит в отдельном процессе Python 3.14; исторический модуль загружается из зафиксированного ZIP. Десять классов сценариев повторены с seed 0–4. Сеть и платная модель в корпусе отключены. raw.csv, парные разности, агрегаты, метаданные и полные JSON-трассы сохранены. Независимый скрипт пересчитывает исходы и средние по трассам.")
p("Нарушение политики задаётся до подсчёта: принятие чужого или неправильно типизированного результата, падение на malformed result, ложное завершение работника, победа отрицательной ставки или неразрешённая операция с полномочиями. Корректный исход требует отсутствия такого нарушения и сохранения ожидаемого числа завершённых задач. Для HTTP 429 ожидается честный частичный результат 3/4 с ошибкой arXiv; для обычного поиска — 4/4. Время wall_ms включает старт процесса и планирование ОС; фиксированный порядок версий и пять повторов не позволяют делать статистический вывод о малой разнице времени.")
doc.add_page_break()
h("4. Результаты внедрения отказов")
rows = []
for name, label in (("normal", "Обычный поиск"), ("wrong_run_result", "Чужой run"),
                    ("malformed_result", "Ошибка формата"), ("source_mismatch", "Подмена типа"),
                    ("forged_shutdown", "Ложный shutdown"), ("malicious_bid", "Ставка −1"),
                    ("source_429", "HTTP 429"), ("wrong_correlation", "Чужой correlation"),
                    ("forbidden_delegate", "Делегирование"), ("resource_owner", "Чужой ресурс")):
    a, b = by[name, "baseline"], by[name, "protected"]
    rows.append((label, f'{a["policy_violations"]}/5', f'{b["policy_violations"]}/5',
                 f'{a["correct_outcomes"]}/5', f'{b["correct_outcomes"]}/5'))
table(["Сценарий", "Наруш. до", "Наруш. после", "Корр. до", "Корр. после"], rows)
picture(FIG / "policy_violations.png", "Рисунок 2 — Нарушения политики по сценариям; данные из 100 трасс", 15.2)
p("На историческом коде сообщение с чужим run было принято как результат; malformed result завершал исследование исключением; материал новостного типа попадал в научную задачу; чужой shutdown вызывал переназначение; отрицательная ставка выигрывала конкурс. Все пять дефектов повторились по пять раз. Защищённая версия отклонила или изолировала воздействие и завершила поиск. В двух случаях отклонение результата потребовало переназначения: среднее время выросло примерно с 36–37 до 76–77 мс. При ложном shutdown среднее время снизилось с 169 до 36 мс, поскольку не понадобилось ожидать и переназначать. При обычном поиске средние значения 34,87 и 35,74 мс; различие меньше обоснованной точности данного стенда.")
p("Существующие ограничения уже действовали в четырёх классах: отказ HTTP 429 оставлял частичный результат; чужой correlation, запрещённое делегирование и расход чужого резервирования отклонялись. Они включены как контроль сохранения защиты. Падений было 5/50 в исторической и 0/50 в защищённой версии. Парные разности и счёт сообщений доступны в приложенных данных.")
h("5. Доказательный контур и испытание модели")
p("Первая схема сверяла ID и точное присутствие цитаты, но могла принять произвольное научное утверждение рядом с настоящим фрагментом. Исправленный контракт не содержит поля подтверждённого пересказа: программа заранее выделяет дословные фрагменты аннотации и заголовка, модель выбирает только их ID. Программа проверяет принадлежность ID текущему контексту и возвращает текст из источника. Тема, категория связи и объяснение маркируются как непроверенная интерпретация; поддержка научного утверждения не оценивается, новостное утверждение не проверено. Статус пригодности означает успешную техническую проверку предварительной аналитики, а не доказанность её смысла. Старый несовместимый формат отклоняется в обычном режиме.")
p(f'Исходные восемь авторских имитаций сохранены без изменения. В новом отдельном корпусе {new_llm["cases"]} целевых случаев получено {new_llm["correct"]}/{new_llm["cases"]} ожидаемых исходов; все {new_llm["normal"]} обычных случая дали пригодный предварительный результат. Ранее структурный валидатор принимал необоснованное утверждение с подлинной цитатой; новый результат сохраняет этот текст только как непроверенную интерпретацию и не выдаёт подтверждённого научного вывода. Составная цитата, выдуманный ID, запрещённая категория и действие отклоняются. Слова system, instruction и ignore в обычном тексте не служат причиной отказа.')
p(f'Первый исторический реальный ответ Qwen стоимостью ${live["actual_cost_usd"]:.8f} отклонён за составную цитату. В шести новых коротких вызовах на настоящих материалах первые три ответа отклонены за слишком длинное объяснение; после явного ограничения длины и уточнения тематической связи все три повторных ответа прошли техническую проверку. Их содержательная оценка: пересечение по теме океанического микропластика без прямого подтверждения, несвязанность доверия в распределённых системах с загрязнением океана, недостаточность данных при скрытой аннотации. Подтверждённый расход шести вызовов — ${live_first["actual_usd"] + live_second["actual_usd"]:.8f}. Эти наблюдения не устанавливают частоту ошибок модели.')
h("6. Воспроизводимость и ограничения")
p("Первоначальные 100 трасс и их агрегаты сохранены без пересчёта. Отдельные новые данные, ожидаемые исходы, ответы модели и ручная оценка приложены в комплекте. Их проверяют независимые скрипты. Тестовый набор содержит 77 автоматических тестов. Архив сдачи распаковывается вне Git; все обязательные проверки работают без сети и ключа OpenRouter. Новые LIVE-вызовы не входят в офлайн-корпус. Синтетические материалы не служат научными доказательствами.")
p("Ограничения измерения: небольшой детерминированный корпус, фиксированный порядок вариантов, таймер ОС и шесть новых реальных генераций Qwen. Дословность фрагмента не доказывает семантическое следование объяснения. Для внешнего развёртывания нужны аутентифицированные отправители, более широкий набор воздействий и независимая экспертная оценка содержательных выводов.")
h("Вывод")
p("Адресные проверки сообщений устранили воспроизведённые отказы в исследованном корпусе. Новый доказательный контракт оставляет подтверждаемыми только дословные фрагменты; тематическое объяснение модели остаётся предварительным. Три пригодных реальных ответа показывают практическую возможность осторожной аналитики, но не гарантируют истинность интерпретации или стабильную долю успешных ответов.")
h("Источники и данные")
p("[1] ResearchRadar MAS, исторический исходный код и защищённый коммит, идентификаторы в metadata.json. [2] Полные трассы и агрегаты первоначального эксперимента. [3] Отдельные исходные данные и ожидаемые исходы нового анализа. [4] OWASP, LLM01 Prompt Injection, https://genai.owasp.org/llmrisk/llm01-prompt-injection/. [5] Сохранённые ответы Qwen и ручная оценка сопоставлений.")

footer = sec.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
footer.add_run("ResearchRadar MAS · 2026")
target = OUT / "ResearchRadar_MAS_Reliability_Assessment.docx"
doc.save(target)
print(target)
