import numpy as np
import torch
import torch.nn as nn
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import joblib
import time
from tqdm import tqdm

# ====================== ЗАГРУЗКА ДАННЫХ ======================
print("🔄 Загрузка подготовленного датасета...")

data = np.load("lstm_dataset.npz")
X_train = data['X_train']
y_train = data['y_train']
X_val   = data['X_val']
y_val   = data['y_val']

scaler_X = joblib.load("scaler_X.pkl")
scaler_y = joblib.load("scaler_y.pkl")

print(f"✅ Данные загружены: Train = {X_train.shape}, Val = {X_val.shape}")

# ====================== ПЕРЕВОД В ТЕНЗОРЫ ======================
X_train_t = torch.tensor(X_train, dtype=torch.float32)
y_train_t = torch.tensor(y_train, dtype=torch.float32)
X_val_t   = torch.tensor(X_val,   dtype=torch.float32)
y_val_t   = torch.tensor(y_val,   dtype=torch.float32)

train_dataset = TensorDataset(X_train_t, y_train_t)
val_dataset   = TensorDataset(X_val_t, y_val_t)

train_loader = DataLoader(train_dataset, batch_size=2048, shuffle=True)
val_loader   = DataLoader(val_dataset,   batch_size=2048, shuffle=False)

# ====================== МОДЕЛЬ LSTM ======================
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
        x = lstm_out[:, -1, :]          # берём последнее состояние
        x = self.bn(x)
        x = self.relu(self.fc1(x))
        x = self.fc2(x)
        return x

model = LSTM_PID()
criterion = nn.MSELoss()
optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-5)
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min',
                                                  factor=0.5, patience=2)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print(f"Model LSTM ({sum(p.numel() for p in model.parameters()):,} params) -> {device}")

# ====================== ОБУЧЕНИЕ ======================
epochs = 15
best_val_loss = float('inf')
train_start = time.time()
current_lr = 0.001

print(f"\nОбучаем {epochs} эпох | Архитектура: LSTM(192) + BN + ReduceLROnPlateau\n")

for epoch in range(epochs):
    model.train()
    train_loss = 0.0
    for X_batch, y_batch in tqdm(train_loader, desc=f"Эпоха {epoch+1}/{epochs}"):
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        
        optimizer.zero_grad()
        outputs = model(X_batch)
        loss = criterion(outputs, y_batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        
        train_loss += loss.item()
    
    # Валидация
    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for X_batch, y_batch in val_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            outputs = model(X_batch)
            val_loss += criterion(outputs, y_batch).item()
    
    avg_train_loss = train_loss / len(train_loader)
    avg_val_loss = val_loss / len(val_loader)
    
    elapsed = time.time() - train_start
    epoch_time = elapsed / (epoch + 1)
    remaining = epoch_time * (epochs - epoch - 1)
    elapsed_str   = time.strftime("%M:%S", time.gmtime(elapsed))
    remaining_str = time.strftime("%M:%S", time.gmtime(remaining))
    current_lr = optimizer.param_groups[0]['lr']
    
    print(f"  [Эпоха {epoch+1:2d}/{epochs}] | Loss: {avg_train_loss:.6f} | Val: {avg_val_loss:.6f} | LR: {current_lr:.5f} | Прошло: {elapsed_str} | Осталось: ~{remaining_str}")
    
    scheduler.step(avg_val_loss)  # Снижаем LR если val_loss не улучшается
    
    if avg_val_loss < best_val_loss:
        best_val_loss = avg_val_loss
        torch.save(model.state_dict(), "best_lstm_pid.pth")
        print("   --> [SОХРАНЕНО] Лучшая модель обновлена!")

print("\n🎉 Обучение завершено!")
print(f"Лучшая валидационная ошибка: {best_val_loss:.6f}")

# Сохраняем финальную модель
torch.save(model.state_dict(), "lstm_pid_final.pth")
print("Модель сохранена как lstm_pid_final.pth")