# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import joblib
import time
from tqdm import tqdm

# ====================== ЗАГРУЗКА ДАННЫХ ======================
print("[INFO] Загрузка датасета...")
data = np.load("lstm_dataset.npz")
X_train = data['X_train']
y_train = data['y_train']
X_val   = data['X_val']
y_val   = data['y_val']
print(f"[OK] Train: {X_train.shape} | Val: {X_val.shape}")

X_train_t = torch.tensor(X_train, dtype=torch.float32)
y_train_t = torch.tensor(y_train, dtype=torch.float32)
X_val_t   = torch.tensor(X_val,   dtype=torch.float32)
y_val_t   = torch.tensor(y_val,   dtype=torch.float32)

train_loader = DataLoader(TensorDataset(X_train_t, y_train_t), batch_size=2048, shuffle=True)
val_loader   = DataLoader(TensorDataset(X_val_t, y_val_t),   batch_size=2048, shuffle=False)

# ====================== АРХИТЕКТУРА (такая же как в train_lstm_model.py) ======================
class LSTM_PID(nn.Module):
    def __init__(self, input_size=9, hidden_size=192, num_layers=2, output_size=3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True, dropout=0.25)
        self.bn   = nn.BatchNorm1d(hidden_size)
        self.fc1  = nn.Linear(hidden_size, 96)
        self.fc2  = nn.Linear(96, output_size)
        self.relu = nn.ReLU()

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        x = lstm_out[:, -1, :]
        x = self.bn(x)
        x = self.relu(self.fc1(x))
        x = self.fc2(x)
        return x

# ====================== ЗАГРУЗКА СОХРАНЁННОЙ МОДЕЛИ ======================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = LSTM_PID().to(device)

print("[INFO] Загружаем best_lstm_pid.pth (лучшие веса до выключения)...")
model.load_state_dict(torch.load("best_lstm_pid.pth", map_location=device, weights_only=True))
print("[OK] Модель загружена успешно!")

# Пониженный LR — дообучаем, а не переучиваем
optimizer = optim.AdamW(model.parameters(), lr=0.0002, weight_decay=1e-5)
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=1)
criterion = nn.MSELoss()

# ====================== ДООБУЧЕНИЕ (3 эпохи: 13, 14, 15) ======================
finetune_epochs = 3
best_val_loss = float('inf')
total_start = time.time()

print(f"\n[START] Дообучение: {finetune_epochs} эпохи (продолжение с 13-й)")
print(f"{'='*65}")

for epoch in range(finetune_epochs):
    epoch_num = 13 + epoch
    epoch_start = time.time()
    elapsed_total = time.time() - total_start
    print(f"\n  ⏱  Начало эпохи {epoch_num}/15 | Общее время: {time.strftime('%M:%S', time.gmtime(elapsed_total))}")

    model.train()
    train_loss = 0.0
    for X_batch, y_batch in tqdm(train_loader, desc=f"  Эпоха {epoch_num}/15", ncols=80):
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        loss = criterion(model(X_batch), y_batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        train_loss += loss.item()

    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for X_batch, y_batch in val_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            val_loss += criterion(model(X_batch), y_batch).item()

    avg_train = train_loss / len(train_loader)
    avg_val   = val_loss   / len(val_loader)
    lr_now    = optimizer.param_groups[0]['lr']

    epoch_dur     = time.time() - epoch_start
    elapsed_total = time.time() - total_start
    epochs_left   = finetune_epochs - epoch - 1
    eta           = epoch_dur * epochs_left

    print(f"  {'─'*60}")
    print(f"  Эпоха {epoch_num}/15 завершена!")
    print(f"    Train Loss : {avg_train:.6f}")
    print(f"    Val Loss   : {avg_val:.6f}")
    print(f"    LR         : {lr_now:.6f}")
    print(f"    Время эпохи: {time.strftime('%M:%S', time.gmtime(epoch_dur))}")
    print(f"    Прошло всего: {time.strftime('%M:%S', time.gmtime(elapsed_total))}")
    print(f"    Осталось ~  : {time.strftime('%M:%S', time.gmtime(eta))}")
    print(f"  {'─'*60}")

    scheduler.step(avg_val)

    if avg_val < best_val_loss:
        best_val_loss = avg_val
        torch.save(model.state_dict(), "best_lstm_pid.pth")
        print("   --> [СОХРАНЕНО] Новый лучший результат!")

# Сохраняем финальную модель
torch.save(model.state_dict(), "lstm_pid_final.pth")
print(f"\n[DONE] Дообучение завершено! Лучшая val loss: {best_val_loss:.6f}")
print("[INFO] Запускаем export_to_torchscript.py...")
