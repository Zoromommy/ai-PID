# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import numpy as np
import torch
import joblib
import json
import os
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Раздаём дашборд как статические файлы
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== КЛАССЫ СИМУЛЯТОРОВ ======================
class FurnaceSimulator:
    def __init__(self):
        self.t = 25.0
        self.valve_prev = 0.0
        self.heat_inertia = 0.0
        self.delay_buffer = [25.0] * 8

    def step(self, valve_target, gas_press, oxygen_press, gas_leak=0.0, dt=0.1):
        # Пневмопривод КФП: ~15%/сек, полный ход ~6.7 сек (идентично обучающему симулятору)
        valve_rate = np.clip(valve_target - self.valve_prev, -15, 15)
        valve = self.valve_prev + valve_rate * dt
        self.valve_prev = valve

        combustion_eff = oxygen_press ** 1.12 * 0.94
        heat_input = valve * 0.985 * gas_press * combustion_eff
        # Теплопотери идентичны обучению: 0.0185 с учётом утечек (gas_leak=0 в норм. режиме)
        heat_loss = (self.t - 25.0) * 0.0185 * (1 + gas_leak * 0.68)

        self.heat_inertia = 0.71 * self.heat_inertia + 0.29 * heat_input
        delayed_heat = self.delay_buffer.pop(0)
        self.delay_buffer.append(self.heat_inertia)

        noise = np.random.normal(0, 0.13 if self.t > 600 else 0.07)
        self.t = self.t + (delayed_heat - heat_loss) * dt + noise
        self.t = max(20.0, min(self.t, 1700.0))
        return self.t, valve

class PIDController:
    def __init__(self, Kp, Ki, Kd):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.integral = 0.0
        self.prev_error = 0.0
        
    def compute(self, error, Kp=None, Ki=None, Kd=None):
        if Kp is not None: self.Kp = Kp
        if Ki is not None: self.Ki = Ki
        if Kd is not None: self.Kd = Kd
        
        valve_unclamped = self.Kp * error + self.Ki * self.integral + self.Kd * (error - self.prev_error)
        
        if not ((valve_unclamped >= 100 and error > 0) or (valve_unclamped <= 0 and error < 0)):
            self.integral += error
            
        self.integral = np.clip(self.integral, -1000.0, 1000.0)
        
        derivative = error - self.prev_error
        valve = self.Kp * error + self.Ki * self.integral + self.Kd * derivative
        self.prev_error = error
        return np.clip(valve, 0, 100)

# ====================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ======================
class SimulationState:
    def __init__(self):
        self.is_running = False
        self.target_sp = 1575.0
        self.gas_press = 1.0
        self.oxygen_press = 1.0
        
        self.sim_ai = FurnaceSimulator()
        self.sim_pid = FurnaceSimulator()
        # ИИ-ПИД: стартует с базой Учителя, нейросеть динамически меняет коэффициенты
        self.pid_ai = PIDController(0.5, 0.04, 1.5)
        # Классический ПИД: те же базовые коэффициенты, что у Учителя — честное сравнение.
        # Разница лишь одна: классика ФИКСИРОВАНА, ИИ — АДАПТИРУЕТСЯ.
        self.pid_classic = PIDController(0.5, 0.04, 1.5)
        
        self.iteration = 0
        self.history = []
        
        init_features = [0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 25.0, 0.0, 1.0]
        self.sequence_buffer = [init_features.copy() for _ in range(20)]
        
        self.current_kp = 0.5
        self.current_ki = 0.04
        self.current_kd = 1.5
        
        # Модель загружаем при старте сервера
        try:
            self.model = torch.jit.load("lstm_pid_torchscript.pt")
            self.model.eval()
            self.scaler_X = joblib.load("scaler_X.pkl")
            self.scaler_y = joblib.load("scaler_y.pkl")
            print("[OK] AI Model loaded!")
        except Exception as e:
            print("[WARN] Model load error:", e)

    def reset(self):
        self.__init__()

state = SimulationState()
clients = []

# ====================== API ДЛЯ УПРАВЛЕНИЯ ======================
class Controls(BaseModel):
    is_running: bool
    target_sp: float
    gas_press: float
    oxygen_press: float
    reset: bool = False

@app.post("/api/controls")
async def update_controls(controls: Controls):
    if controls.reset:
        state.reset()
        return {"status": "reset"}
        
    state.is_running = controls.is_running
    state.target_sp = controls.target_sp
    state.gas_press = controls.gas_press
    state.oxygen_press = controls.oxygen_press
    return {"status": "updated"}

@app.get("/api/state")
async def get_state():
    return {
        "is_running": state.is_running,
        "target_sp": state.target_sp,
        "gas_press": state.gas_press,
        "oxygen_press": state.oxygen_press
    }

# ====================== WEBSOCKET ДЛЯ ДАШБОРДА ======================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            # Отправляем последние данные клиентам (или пустой пакет, если история пуста)
            if len(state.history) > 0:
                await websocket.send_text(json.dumps(state.history[-1]))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        clients.remove(websocket)

# ====================== ЦИКЛ СИМУЛЯЦИИ (BACKGROUND) ======================
async def simulation_loop():
    while True:
        if state.is_running:
            # --- 1. AI СИСТЕМА ---
            error_ai = state.target_sp - state.sim_ai.t
            error_deriv_ai = error_ai - state.pid_ai.prev_error
            total_eff = state.gas_press * state.oxygen_press
            
            current_features = [
                error_ai, error_deriv_ai, state.pid_ai.integral, 
                state.gas_press, state.oxygen_press, 0.0, 
                state.sim_ai.t, state.sim_ai.valve_prev, total_eff
            ]
            
            state.sequence_buffer.pop(0)
            state.sequence_buffer.append(current_features)
            
            seq = np.array(state.sequence_buffer)
            seq_scaled = state.scaler_X.transform(seq)
            seq_tensor = torch.tensor(seq_scaled, dtype=torch.float32).unsqueeze(0)
            
            with torch.no_grad():
                pred_scaled = state.model(seq_tensor)
                pred = state.scaler_y.inverse_transform(pred_scaled.numpy())[0]
                
            Kp_ai, Ki_ai, Kd_ai = pred

            # Пол = классический ПИД
            Kp_ai = float(np.clip(Kp_ai, 0.5,  3.0))
            Ki_ai = float(np.clip(Ki_ai, 0.04, 0.5))
            Kd_ai = float(np.clip(Kd_ai, 1.5, 12.0))

            # Экспоненциальное сглаживание: плавная смена коэффициентов
            # Alpha=0.15: новый коэф влияет на 15%, старый удерживает 85%
            # Это убирает скачки 0.5→2.5→0.5 каждые 0.1сек → стабильность
            ALPHA = 0.15
            state.current_kp = ALPHA * Kp_ai + (1 - ALPHA) * state.current_kp
            state.current_ki = ALPHA * Ki_ai + (1 - ALPHA) * state.current_ki
            state.current_kd = ALPHA * Kd_ai + (1 - ALPHA) * state.current_kd

            Kp_ai = state.current_kp
            Ki_ai = state.current_ki
            Kd_ai = state.current_kd

            valve_ai_target = state.pid_ai.compute(error_ai, Kp_ai, Ki_ai, Kd_ai)
            # gas_leak=0.0: нормальный режим работы (без утечек тепла)
            t_ai, valve_ai_real = state.sim_ai.step(valve_ai_target, state.gas_press, state.oxygen_press, gas_leak=0.0)

            # --- 2. КЛАССИЧЕСКАЯ СИСТЕМА (фиксированный ПИД, те же базовые коэффы) ---
            error_pid = state.target_sp - state.sim_pid.t
            valve_pid_target = state.pid_classic.compute(error_pid)
            t_pid, valve_pid_real = state.sim_pid.step(valve_pid_target, state.gas_press, state.oxygen_press, gas_leak=0.0)
            
            # --- 3. СОХРАНЕНИЕ ---
            state.iteration += 1
            current_time = state.iteration * 0.1
            
            data_point = {
                "time": current_time,
                "target": state.target_sp,
                "ai_temp": t_ai,
                "pid_temp": t_pid,
                "kp_ai": float(Kp_ai),
                "ki_ai": float(Ki_ai),
                "kd_ai": float(Kd_ai),
                "valve_ai":  round(float(valve_ai_real), 1),
                "valve_pid": round(float(valve_pid_real), 1),
                "eff_percent": max(0.0, min(100.0, (state.gas_press * state.oxygen_press * 100)))
            }
            
            state.history.append(data_point)
            if len(state.history) > 1000:
                state.history.pop(0)
                
        await asyncio.sleep(0.1)  # 10Hz tick

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulation_loop())

if __name__ == "__main__":
    import uvicorn
    # Запуск на 0.0.0.0 делает сервер доступным для всех устройств в сети
    uvicorn.run(app, host="0.0.0.0", port=8000)
