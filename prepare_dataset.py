import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import glob
import os
import joblib

print("🔄 Загрузка датасета...")

files = glob.glob("pid_dataset_*.parquet")
if not files:
    print("❌ Файл датасета не найден!")
    exit()

latest_file = max(files, key=os.path.getctime)
print(f"✅ Загружен файл: {latest_file}")
df = pd.read_parquet(latest_file)

print(f"📊 Размер датасета: {len(df):,} записей\n")

sequence_length = 20
features = ['error', 'error_deriv', 'error_integral', 'gas_press', 
            'oxygen_press', 'gas_leak', 'temperature', 'valve', 'total_eff']

print("🔄 Создание последовательностей (sequences) для LSTM (Оптимизировано Numpy)...")

# Ультрабыстрое создание окон через numpy stride_tricks
df_vals = df[features].values
targets = df[['Kp_target', 'Ki_target', 'Kd_target']].values

shape = (df_vals.shape[0] - sequence_length + 1, sequence_length, df_vals.shape[1])
strides = (df_vals.strides[0], df_vals.strides[0], df_vals.strides[1])
X = np.lib.stride_tricks.as_strided(df_vals, shape=shape, strides=strides)

y = targets[sequence_length - 1:]

# Копируем массивы для памяти
X = X.copy()
y = y.copy()

print(f"✅ Создано последовательностей: {X.shape[0]:,}")

print("\n📏 Нормализация данных...")
scaler_X = MinMaxScaler()
scaler_y = MinMaxScaler()

X_reshaped = X.reshape(-1, X.shape[-1])
X_scaled = scaler_X.fit_transform(X_reshaped).reshape(X.shape)
y_scaled = scaler_y.fit_transform(y)

split_idx = int(len(X_scaled) * 0.8)
val_idx = int(len(X_scaled) * 0.9)

X_train, X_val, X_test = X_scaled[:split_idx], X_scaled[split_idx:val_idx], X_scaled[val_idx:]
y_train, y_val, y_test = y_scaled[:split_idx], y_scaled[split_idx:val_idx], y_scaled[val_idx:]

print(f"\n📊 Разделение датасета:")
print(f"Train: {X_train.shape[0]:,} | Validation: {X_val.shape[0]:,} | Test: {X_test.shape[0]:,}")

print("\n💾 Сохранение...")
np.savez_compressed("lstm_dataset.npz",
                    X_train=X_train, y_train=y_train,
                    X_val=X_val, y_val=y_val,
                    X_test=X_test, y_test=y_test)

joblib.dump(scaler_X, "scaler_X.pkl")
joblib.dump(scaler_y, "scaler_y.pkl")

print("🎉 Готово! Переходите к train_lstm_model.py")
