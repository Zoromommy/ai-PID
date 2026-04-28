import torch
import joblib
import numpy as np
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ====================== ОПРЕДЕЛЕНИЕ МОДЕЛИ ======================
class LSTM_PID(torch.nn.Module):
    def __init__(self, input_size=9, hidden_size=192, num_layers=2, output_size=3):
        super().__init__()
        self.lstm = torch.nn.LSTM(input_size, hidden_size, num_layers,
                                  batch_first=True, dropout=0.25)
        self.bn   = torch.nn.BatchNorm1d(hidden_size)
        self.fc1  = torch.nn.Linear(hidden_size, 96)
        self.fc2  = torch.nn.Linear(96, output_size)
        self.relu = torch.nn.ReLU()

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        x = lstm_out[:, -1, :]      # берём последнее состояние
        x = self.bn(x)
        x = self.relu(self.fc1(x))
        x = self.fc2(x)
        return x

# ====================== ЗАГРУЗКА И ЭКСПОРТ ======================
print("Загружаем обученную модель...")

model = LSTM_PID()
model.load_state_dict(torch.load("best_lstm_pid.pth", map_location=torch.device('cpu')))
model.eval()

# Пример входных данных для трассировки
example_input = torch.randn(1, 20, 9)   # batch=1, sequence=20, features=9

# Экспорт в TorchScript
scripted_model = torch.jit.trace(model, example_input)

# Сохраняем
scripted_model.save("lstm_pid_torchscript.pt")
print("✅ Модель успешно экспортирована в TorchScript!")
print("Файл сохранён: lstm_pid_torchscript.pt")

# Проверка
test_input = torch.randn(1, 20, 9)
output = scripted_model(test_input)
print(f"Проверка прошла. Выход модели: {output.shape}")