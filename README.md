# 🔥 AI-Адаптивный ПИД-Регулятор Печи КФП

> **Интеллектуальная система управления кислородно-факельной печью на базе нейросети LSTM**  
> Алмалыкский ГМК (АГМК) · МПЗ · Температура до 1700°C

---

## 📌 О проекте

Данный проект реализует **адаптивный ПИД-регулятор**, где коэффициенты Kp, Ki, Kd динамически предсказываются нейросетью **LSTM** в режиме реального времени. Система сравнивается с классическим фиксированным ПИД-регулятором и демонстрирует превосходство по точности, скорости выхода на режим и расходу газа.

### ✨ Ключевые особенности
- 🧠 **LSTM нейросеть** предсказывает оптимальные Kp, Ki, Kd каждые 0.1 сек
- ⚙️ **Параллельная симуляция**: AI vs Классический ПИД в реальном времени
- 📊 **5-страничный дашборд** с графиками, метриками ISE и экономическим анализом
- 💰 **Расчёт экономии** газа в м³ и стоимости в UZS
- 🌐 **Сетевой доступ** — сервер доступен с любого устройства в локальной сети

---

## 🏗️ Архитектура системы

```
generate_dataset.py   →  prepare_dataset.py   →  train_lstm_model.py
    (1.85M строк)           (LSTM sequences)        (15 эпох, AdamW)
                                                          ↓
                                                  finetune_lstm.py
                                                  (дообучение 3 эп.)
                                                          ↓
                                             export_to_torchscript.py
                                               (lstm_pid_torchscript.pt)
                                                          ↓
                                                       main.py
                                                (FastAPI + WebSocket)
                                                          ↓
                                                dashboard/ (HTML/JS/CSS)
```

---

## 🧠 Модель LSTM

| Параметр | Значение |
|----------|----------|
| Входные признаки | 9 (error, error_deriv, integral, gas_press, O2_press, gas_leak, temp, valve, total_eff) |
| Длина последовательности | 20 шагов (2 сек истории) |
| Архитектура | LSTM(192) × 2 + BatchNorm + FC(96) → [Kp, Ki, Kd] |
| Dropout | 0.25 |
| Оптимизатор | AdamW (lr=0.001, weight_decay=1e-5) |
| Планировщик LR | ReduceLROnPlateau |
| Выход | Kp∈[0.5, 3.0], Ki∈[0.04, 0.5], Kd∈[1.5, 12.0] |

---

## 🖥️ Дашборд

| Страница | Описание |
|----------|----------|
| 🏠 Главная | Навигационное меню |
| 📡 Телеметрия | Температура AI vs ПИД, управление уставкой и давлениями |
| 🧠 Адаптация | Графики Kp, Ki, Kd в реальном времени |
| 📈 Аналитика | ISE, макс. отклонение, сравнительный блок превосходства |
| 🗄️ Ресурсы | Накопительный расход газа и O₂ в м³ |
| 💵 Экономика | Стоимость газа в UZS, сравнение затрат |

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install fastapi uvicorn torch numpy joblib scikit-learn pandas tqdm
```

### 2. Запуск сервера

```bash
python main.py
```

Или двойной клик на `Запуск_Сервера.bat`

### 3. Открыть дашборд

```
http://localhost:8000
```

Для доступа с другого устройства в сети:
```
http://<IP-компьютера>:8000
```

---

## 📁 Структура файлов

```
├── main.py                    # FastAPI сервер + симуляция
├── generate_dataset.py        # Генерация обучающих данных (TeacherPID)
├── prepare_dataset.py         # Подготовка последовательностей для LSTM
├── train_lstm_model.py        # Обучение LSTM модели
├── finetune_lstm.py           # Дообучение (fine-tuning)
├── export_to_torchscript.py   # Экспорт в TorchScript для production
├── generate_report.py         # Автогенерация Word-отчёта
├── lstm_pid_torchscript.pt    # Готовая модель (TorchScript)
├── scaler_X.pkl               # Нормализатор входных данных
├── scaler_y.pkl               # Нормализатор выходных данных
├── Запуск_Сервера.bat         # Скрипт запуска (Windows)
├── dashboard/
│   ├── index.html             # Интерфейс дашборда
│   ├── app.js                 # WebSocket + Chart.js логика
│   └── style.css              # Тёмная тема, анимации
└── Trial_Report_AI_Furnace.docx  # Полный технический отчёт
```

> **Примечание:** Файлы `lstm_dataset.npz` (165MB) и `pid_dataset_*.parquet` (154MB) не включены в репозиторий из-за ограничений GitHub. Для их воссоздания запустите `generate_dataset.py` → `prepare_dataset.py`.

---

## ⚡ Технологии

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![PyTorch](https://img.shields.io/badge/PyTorch-2.x-orange?logo=pytorch)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)
![Chart.js](https://img.shields.io/badge/Chart.js-4.4-pink?logo=chartdotjs)
![JavaScript](https://img.shields.io/badge/JavaScript-ES2023-yellow?logo=javascript)

---

## 📄 Лицензия

MIT License — свободное использование с указанием авторства.
