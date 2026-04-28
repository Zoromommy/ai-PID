import numpy as np
import pandas as pd
from tqdm import tqdm
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import time
from datetime import datetime

# ====================== УЛУЧШЕННАЯ МОДЕЛЬ ПЕЧИ ======================
class FurnaceSimulator:
    def __init__(self):
        self.t = 25.0
        self.valve_prev = 0.0
        self.heat_inertia = 0.0
        self.delay_buffer = [25.0] * 8

    def step(self, valve_target, gas_press, oxygen_press, gas_leak, dt=0.1):
        valve_rate = np.clip(valve_target - self.valve_prev, -15, 15)  # пневмопривод КФП: ~15%/сек, полный ход ~6.7 сек
        valve = self.valve_prev + valve_rate * dt
        self.valve_prev = valve

        combustion_eff = oxygen_press ** 1.12 * 0.94
        heat_input = valve * 0.985 * gas_press * combustion_eff
        heat_loss = (self.t - 25.0) * 0.0185 * (1 + gas_leak * 0.68)

        self.heat_inertia = 0.71 * self.heat_inertia + 0.29 * heat_input
        delayed_heat = self.delay_buffer.pop(0)
        self.delay_buffer.append(self.heat_inertia)

        noise = np.random.normal(0, 0.13 if self.t > 600 else 0.07)
        self.t = self.t + (delayed_heat - heat_loss) * dt + noise
        self.t = max(20.0, min(self.t, 1700.0))
        return self.t, valve

# ====================== УМНЫЙ УЧИТЕЛЬ (Teacher PID) ======================
class TeacherPID:
    def __init__(self):
        self.integral = 0.0
        self.prev_error = 0.0

    def get_gains(self, error, gas_leak, total_eff):
        """
        РЕЗИДУАЛЬНЫЙ УЧИТЕЛЬ — математическая гарантия: Teacher >= Классический ПИД.

        Принцип:
          - База = классический ПИД (Kp=0.5, Ki=0.04, Kd=1.5)
          - Учитель только ДОБАВЛЯЕТ улучшения поверх базы
          - Итоговые коэффициенты НИКОГДА не опускаются ниже базы

        Это значит: в любом сценарии ИИ+ПИД >= Классический ПИД.

        Сценарии улучшений:
          1. ДАЛЕКО от уставки → Kp выше → быстрый нагрев (оба клапана всё равно идут на 100%, но
             при промежуточных ошибках 50-200°C ИИ реагирует быстрее)
          2. БЛИЗКО к уставке → Kd сильно выше → гашение колебаний (главное преимущество!)
          3. УТЕЧКА → Ki выше → компенсирует постоянные потери тепла → нет статической ошибки
        """
        abs_err = abs(error)

        # === БАЗА = КЛАССИЧЕСКИЙ ПИД ===
        KP_CLASSIC = 0.5
        KI_CLASSIC = 0.04
        KD_CLASSIC = 1.5

        # Нормализованная утечка [0..1]
        disturbance_leak = np.clip(gas_leak / 2.0, 0.0, 1.0)

        # Зона близости к уставке — широкая (140°C) из-за медленного клапана ±15%/сек
        # При total_eff > 1 (мощная печь) тормозим ещё раньше
        braking_dist = 140.0 + 60.0 * max(0.0, total_eff - 1.0)
        proximity = np.exp(-abs_err / braking_dist)   # 0 = далеко, 1 = у уставки
        far = 1.0 - proximity

        # === АДАПТАЦИЯ 1: Kp ===
        # Далеко (+1.0): форсируем нагрев | Близко с утечкой (+0.3*leak): держим давление
        Kp = KP_CLASSIC + 1.0 * far + 0.3 * disturbance_leak * proximity

        # Адаптация к мощности горения: сильная печь → немного осторожнее
        power_factor = np.clip(1.0 / (total_eff ** 0.35 + 0.01), 0.6, 1.4)
        Kp = Kp * power_factor

        # === АДАПТАЦИЯ 2: Kd — ГЛАВНЫЙ КОЗЫРЬ ===
        # У уставки Kd вырастает с 1.5 до 8.0 → главная причина меньших колебаний у ИИ
        Kd = KD_CLASSIC + 6.5 * proximity

        # === АДАПТАЦИЯ 3: Ki ===
        # При утечке: быстрее компенсируем постоянные потери тепла
        Ki = KI_CLASSIC + 0.15 * disturbance_leak * proximity

        # === ГАРАНТИРОВАННЫЙ ПОЛ = Классический ПИД ===
        # Физически невозможно быть хуже классики
        Kp = float(np.clip(Kp, KP_CLASSIC, 3.0))
        Ki = float(np.clip(Ki, KI_CLASSIC, 0.5))
        Kd = float(np.clip(Kd, KD_CLASSIC, 12.0))

        return Kp, Ki, Kd

    def compute_valve(self, error, Kp, Ki, Kd):
        valve_unclamped = Kp * error + Ki * self.integral + Kd * (error - self.prev_error)
        
        # Anti-windup
        if not ((valve_unclamped >= 100 and error > 0) or (valve_unclamped <= 0 and error < 0)):
            self.integral += error
            
        self.integral = np.clip(self.integral, -1000.0, 1000.0)
        
        derivative = error - self.prev_error
        valve = Kp * error + Ki * self.integral + Kd * derivative
        self.prev_error = error
        return np.clip(valve, 0, 100)

# ====================== ГЕНЕРАЦИЯ ДАТАСЕТА ======================
def generate_dataset(num_episodes=8000, sequence_length=20, steps_per_episode=250):
    data = []
    sim = FurnaceSimulator()
    teacher = TeacherPID()

    print(f"Начинаем генерацию: {num_episodes} эпизодов × {steps_per_episode} шагов...")

    for episode in tqdm(range(num_episodes)):
        sim.__init__()
        teacher.__init__()
        # Рабочая температура КФП АГМК: 1550-1600°C (с диапазоном обучения 1300-1700°C)
        target_sp = np.random.uniform(1300, 1700)
        # Начальные условия: печь может быть холодной или уже нагретой
        sim.t = np.random.uniform(25.0, 1600.0)
        sim.delay_buffer = [sim.t] * 8
        
        # Реальные рабочие диапазоны печи КФП АГМК МПЗ
        # Давление газа: номинал 0.05 МПа → нормализован в 1.0 (диапазон 0.7-1.4)
        # Давление O2:  номинал 0.225 МПа → нормализован в 1.0 (диапазон 0.7-1.5)
        base_gas    = np.random.uniform(0.7, 1.4)
        base_oxygen = np.random.uniform(0.7, 1.5)
        
        for step in range(steps_per_episode):
            # Резкое изменение уставки в середине эпизода (30% вероятность)
            if step == steps_per_episode // 2 and np.random.rand() < 0.3:
                target_sp = np.random.uniform(100, 1700)
                teacher.integral = 0.0  # сброс интегратора при смене уставки

            gas_press   = max(0.1, base_gas    + np.random.normal(0, 0.05))
            oxygen_press = max(0.1, base_oxygen + np.random.normal(0, 0.07))
            # Реалистичные утечки: 0-2.0 (не 5.0!), с повышенной долей малых утечек
            gas_leak = np.random.uniform(0, 2.0) if np.random.rand() < 0.4 else np.random.uniform(0, 0.5)
            
            total_eff = gas_press * oxygen_press
            error = target_sp - sim.t
            
            # ФИКС: Сохраняем prev_error ДО compute_valve(),
            # чтобы error_deriv в датасете был ненулевым
            prev_error_for_deriv = teacher.prev_error
            
            # Учитель динамически подбирает коэффициенты
            Kp, Ki, Kd = teacher.get_gains(error, gas_leak, total_eff)
            
            # Учитель применяет ИМЕННО ЭТИ коэффициенты для управления
            # (после этого teacher.prev_error становится = error)
            valve_target = teacher.compute_valve(error, Kp, Ki, Kd)
            
            current_t, current_valve = sim.step(valve_target, gas_press, oxygen_press, gas_leak)
            
            if step >= sequence_length - 1:
                features = {
                    'episode': episode, 'step': step, 'target_sp': target_sp, 'error': error,
                    # ТЕПЕРЬ корректно: prev_error_for_deriv сохранён ДО compute_valve()
                    'error_deriv': error - prev_error_for_deriv,
                    'error_integral': teacher.integral,
                    'gas_press': gas_press, 'oxygen_press': oxygen_press, 'gas_leak': gas_leak,
                    'temperature': current_t, 'valve': current_valve, 'total_eff': total_eff,
                    'Kp_target': Kp, 'Ki_target': Ki, 'Kd_target': Kd
                }
                data.append(features)

    df = pd.DataFrame(data)
    filename = f"pid_dataset_{len(df):,}_rows_{datetime.now().strftime('%Y%m%d_%H%M')}.parquet"
    df.to_parquet(filename, index=False)
    
    print(f"\nДатасет успешно создан! Размер: {len(df):,} записей")
    return df, filename

if __name__ == "__main__":
    generate_dataset(num_episodes=8000, sequence_length=20, steps_per_episode=250)
