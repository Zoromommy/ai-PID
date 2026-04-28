// ====================== STATE ======================
const MAX_POINTS = 300;
let isRunning = false;
let ws = null;
let wsConnected = false;

let times = [], aiTemps = [], pidTemps = [], targets = [];
let kpData = [], kiData = [], kdData = [];

let targetSP = 1575;
let gasPress = 1.0, oxyPress = 1.0;
let lastMetricsUpdate = 0;

let totGasAI = 0, totOxyAI = 0, totGasPID = 0, totOxyPID = 0;
let segGasAI = 0, segOxyAI = 0, segGasPID = 0, segOxyPID = 0;
let lastLogMinute = 0;
let valveTravelAI = 0, valveTravelPID = 0;
let prevValveAI = 0, prevValvePID = 0;

const chartDefaults = {
  borderWidth: 2, pointRadius: 0, tension: 0.4, fill: false
};

const tempCtx = document.getElementById('tempChart').getContext('2d');
const tempChart = new Chart(tempCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      { label: 'Адаптивный регулятор', data: [], borderColor: '#818cf8', ...chartDefaults },
      { label: 'Классический ПИД',       data: [], borderColor: '#38bdf8', ...chartDefaults },
      { label: 'Уставка',            data: [], borderColor: 'rgba(255,255,255,0.3)', borderDash: [6,4], ...chartDefaults },
      // КФП зоны: жёлтые предупредительные границы
      { label: 'Граница 1500°C', data: [], borderColor: '#facc15', borderWidth: 1.5, borderDash: [8,4], pointRadius: 0, tension: 0, fill: false },
      { label: 'Граница 1650°C', data: [], borderColor: '#facc15', borderWidth: 1.5, borderDash: [8,4], pointRadius: 0, tension: 0, fill: false },
      // Зелёные рабочие границы КФП
      { label: 'Зона КФП 1550°C', data: [], borderColor: '#4ade80', borderWidth: 1.5, borderDash: [4,4], pointRadius: 0, tension: 0, fill: false },
      { label: 'Зона КФП 1600°C', data: [], borderColor: '#4ade80', borderWidth: 1.5, borderDash: [4,4], pointRadius: 0, tension: 0, fill: false },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { 
        grid: { color: 'rgba(255,255,255,0.05)' }, 
        ticks: { 
          color: '#64748b', 
          maxTicksLimit: 10, 
          callback: function(val, index) { 
            const timeVal = this.getLabelForValue(val);
            return timeVal !== undefined ? Number(timeVal).toFixed(0) + 's' : ''; 
          } 
        } 
      },
      y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' }, title: { display: true, text: 'Температура (°C)', color: '#64748b' } }
    }
  }
});

const gainCtx = document.getElementById('gainChart').getContext('2d');
const gainChart = new Chart(gainCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      { label: 'Kp', data: [], borderColor: '#f59e0b', ...chartDefaults },
      { label: 'Ki', data: [], borderColor: '#10b981', ...chartDefaults },
      { label: 'Kd', data: [], borderColor: '#f43f5e', ...chartDefaults }
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: true, labels: { color: '#94a3b8', boxWidth: 12, padding: 16 } } },
    scales: {
      x: { 
        grid: { color: 'rgba(255,255,255,0.05)' }, 
        ticks: { 
          color: '#64748b', 
          maxTicksLimit: 10,
          callback: function(val, index) { 
            const timeVal = this.getLabelForValue(val);
            return timeVal !== undefined ? Number(timeVal).toFixed(0) + 's' : ''; 
          } 
        } 
      },
      y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } }
    }
  }
});

const errorCtx = document.getElementById('errorChart').getContext('2d');
const errorChart = new Chart(errorCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      { label: 'Ошибка Адаптивного',  data: [], borderColor: '#818cf8', ...chartDefaults },
      { label: 'Ошибка PID', data: [], borderColor: '#38bdf8', ...chartDefaults }
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: true, labels: { color: '#94a3b8', boxWidth: 12, padding: 16 } } },
    scales: {
      x: { 
        grid: { color: 'rgba(255,255,255,0.05)' }, 
        ticks: { 
          color: '#64748b', 
          maxTicksLimit: 10, 
          callback: function(val, index) { 
            const timeVal = this.getLabelForValue(val);
            return timeVal !== undefined ? Number(timeVal).toFixed(0) + 's' : ''; 
          } 
        } 
      },
      y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' }, title: { display: true, text: 'Ошибка (°C)', color: '#64748b' } }
    }
  }
});

// ====================== WEBSOCKET ======================
function connectWS() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

  ws.onopen = () => {
    wsConnected = true;
    console.log('✅ WebSocket подключён');
  };

  ws.onmessage = (event) => {
    const d = JSON.parse(event.data);
    const t = parseFloat(d.time.toFixed(1));

    times.push(t);
    aiTemps.push(parseFloat(d.ai_temp.toFixed(2)));
    pidTemps.push(parseFloat(d.pid_temp.toFixed(2)));
    targets.push(d.target);
    kpData.push(parseFloat(d.kp_ai.toFixed(4)));
    kiData.push(parseFloat(d.ki_ai.toFixed(4)));
    kdData.push(parseFloat(d.kd_ai.toFixed(4)));

    if (times.length > MAX_POINTS) {
      times.shift(); aiTemps.shift(); pidTemps.shift(); targets.shift();
      kpData.shift(); kiData.shift(); kdData.shift();
    }

    // Расчет накопительного расхода каждую итерацию (0.1 сек)
    if (d.valve_ai !== undefined && d.valve_pid !== undefined) {
      const maxGas = 300, maxOxy = 1500;
      const flowGasAI = (d.valve_ai / 100) * maxGas * gasPress;
      const flowOxyAI = (d.valve_ai / 100) * maxOxy * oxyPress;
      const flowGasPID = (d.valve_pid / 100) * maxGas * gasPress;
      const flowOxyPID = (d.valve_pid / 100) * maxOxy * oxyPress;
      
      // 0.1 сек = 1 / 36000 часа (перевод м³/ч в м³ за 0.1 сек)
      const tickFraction = 0.1 / 3600;
      segGasAI += flowGasAI * tickFraction;
      segOxyAI += flowOxyAI * tickFraction;
      segGasPID += flowGasPID * tickFraction;
      segOxyPID += flowOxyPID * tickFraction;

      valveTravelAI += Math.abs(d.valve_ai - prevValveAI);
      valveTravelPID += Math.abs(d.valve_pid - prevValvePID);
      prevValveAI = d.valve_ai;
      prevValvePID = d.valve_pid;

      const currentSegment = Math.floor(d.time / 10);
      if (currentSegment > lastLogMinute && currentSegment > 0) {
        lastLogMinute = currentSegment;
        
        totGasAI += segGasAI;
        totOxyAI += segOxyAI;
        totGasPID += segGasPID;
        totOxyPID += segOxyPID;
        
        const timeSec = currentSegment * 10;
        const tbody = document.getElementById('consumption-log');
        if (tbody) {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${timeSec} сек</td>
            <td style="color:var(--ai)">${segGasAI.toFixed(2)}</td>
            <td style="color:var(--ai)">${segOxyAI.toFixed(2)}</td>
            <td style="color:var(--pid)">${segGasPID.toFixed(2)}</td>
            <td style="color:var(--pid)">${segOxyPID.toFixed(2)}</td>
          `;
          tbody.appendChild(tr);
          if (tbody.parentElement && tbody.parentElement.parentElement) {
            tbody.parentElement.parentElement.scrollTop = tbody.parentElement.parentElement.scrollHeight;
          }
        }
        
        // ECONOMICS LOGGING
        const ecoTbodyAI = document.getElementById('eco-log-ai');
        const ecoTbodyPID = document.getElementById('eco-log-pid');
        const costAI = segGasAI * 1800;
        const costPID = segGasPID * 1800;
        
        if (ecoTbodyAI) {
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${timeSec} сек</td><td style="color:var(--ai)">${costAI.toFixed(0)} UZS</td>`;
          ecoTbodyAI.appendChild(tr);
          if (ecoTbodyAI.parentElement && ecoTbodyAI.parentElement.parentElement) {
            ecoTbodyAI.parentElement.parentElement.scrollTop = ecoTbodyAI.parentElement.parentElement.scrollHeight;
          }
        }
        if (ecoTbodyPID) {
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${timeSec} сек</td><td style="color:var(--pid)">${costPID.toFixed(0)} UZS</td>`;
          ecoTbodyPID.appendChild(tr);
          if (ecoTbodyPID.parentElement && ecoTbodyPID.parentElement.parentElement) {
            ecoTbodyPID.parentElement.parentElement.scrollTop = ecoTbodyPID.parentElement.parentElement.scrollHeight;
          }
        }
        
        // Обновление карточек расхода (итогов) строго при добавлении строки в таблицу
        animateNumber('tot-gas-ai', totGasAI, '', 2);
        animateNumber('tot-gas-pid', totGasPID, '', 2);
        animateNumber('tot-oxy-ai', totOxyAI, '', 2);
        animateNumber('tot-oxy-pid', totOxyPID, '', 2);
        
        // Сброс сегмента для подсчета следующих 10 секунд
        segGasAI = 0; segOxyAI = 0; segGasPID = 0; segOxyPID = 0;
      }
    }

    updateCharts();
    
    const now = Date.now();
    if (now - lastMetricsUpdate >= 2000) {
      updateMetrics(d);
      updateEconomics(d.time);
      lastMetricsUpdate = now;
    }
  };

  ws.onclose = () => {
    wsConnected = false;
    setTimeout(connectWS, 2000); // авто-переподключение
  };

  ws.onerror = () => ws.close();
}

function updateCharts() {
  const n = times.length;
  // Temperature chart
  tempChart.data.labels = times;
  tempChart.data.datasets[0].data = aiTemps;
  tempChart.data.datasets[1].data = pidTemps;
  tempChart.data.datasets[2].data = targets;
  // КФП зоны — горизонтальные линии на весь видимый диапазон
  tempChart.data.datasets[3].data = Array(n).fill(1500);
  tempChart.data.datasets[4].data = Array(n).fill(1650);
  tempChart.data.datasets[5].data = Array(n).fill(1550);
  tempChart.data.datasets[6].data = Array(n).fill(1600);
  tempChart.update('none');

  // Gain chart
  gainChart.data.labels = times;
  gainChart.data.datasets[0].data = kpData;
  gainChart.data.datasets[1].data = kiData;
  gainChart.data.datasets[2].data = kdData;
  gainChart.update('none');

  // Error chart
  const errAI  = aiTemps.map((v,i) => parseFloat((targets[i] - v).toFixed(2)));
  const errPID = pidTemps.map((v,i) => parseFloat((targets[i] - v).toFixed(2)));
  errorChart.data.labels = times;
  errorChart.data.datasets[0].data = errAI;
  errorChart.data.datasets[1].data = errPID;
  errorChart.update('none');
}

function animateNumber(elementId, newValue, suffix = '', precision = 0, prefix = '') {
  const el = document.getElementById(elementId);
  if (!el) return;
  
  const newText = prefix + newValue.toFixed(precision) + suffix;
  if (el.textContent === newText) return;
  
  // Анимация ухода (вверх, размытие, затухание)
  el.style.transition = "transform 0.2s ease-in, opacity 0.2s ease-in, filter 0.2s ease-in";
  el.style.transform = "translateY(-10px)";
  el.style.opacity = "0";
  el.style.filter = "blur(3px)";
  
  setTimeout(() => {
    // Подмена текста
    el.textContent = newText;
    
    // Мгновенный перенос вниз
    el.style.transition = "none";
    el.style.transform = "translateY(10px)";
    
    // Force DOM reflow
    void el.offsetWidth;
    
    // Анимация появления (вверх в центр, фокус, появление) с легким пружинящим эффектом
    el.style.transition = "transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.3s ease-out, filter 0.3s ease-out";
    el.style.transform = "translateY(0)";
    el.style.opacity = "1";
    el.style.filter = "blur(0px)";
  }, 200);
}

function updateMetrics(d) {
  animateNumber('m-ai-temp', d.ai_temp, ' °C', 1);
  animateNumber('m-pid-temp', d.pid_temp, ' °C', 1);

  // Расчет реального расхода (м³/ч)
  if (d.valve_ai !== undefined) {
    const maxGas = 300, maxOxy = 1500;
    const currentGasFlow = (d.valve_ai / 100) * maxGas * gasPress;
    const currentOxyFlow = (d.valve_ai / 100) * maxOxy * oxyPress;
    animateNumber('m-gas-flow', currentGasFlow, ' м³/ч', 0);
    animateNumber('m-oxy-flow', currentOxyFlow, ' м³/ч', 0);
  }

  animateNumber('kp-val', d.kp_ai, '', 4);
  animateNumber('ki-val', d.ki_ai, '', 4);
  animateNumber('kd-val', d.kd_ai, '', 4);

  // ISE & max deviation
  if (aiTemps.length > 1) {
    const iseAI  = aiTemps.reduce((s,v,i) => s + Math.pow(targets[i]-v, 2), 0);
    const isePID = pidTemps.reduce((s,v,i) => s + Math.pow(targets[i]-v, 2), 0);
    const devAI  = Math.max(...aiTemps.map((v,i) => Math.abs(targets[i]-v)));
    const devPID = Math.max(...pidTemps.map((v,i) => Math.abs(targets[i]-v)));
    
    animateNumber('ise-ai', iseAI, '', 0);
    animateNumber('ise-pid', isePID, '', 0);
    animateNumber('dev-ai', devAI, ' °C', 1);
    animateNumber('dev-pid', devPID, ' °C', 1);

    // Блок превосходства
    const supBlock = document.getElementById('superiority-block');
    const supLabel = document.getElementById('sup-label');
    const supValue = document.getElementById('sup-value');
    const supDesc  = document.getElementById('sup-desc');
    if (iseAI > 0 && isePID > 0) {
      if (iseAI < isePID) {
        // ИИ лучше
        const pct = ((isePID - iseAI) / isePID) * 100;
        supLabel.textContent = 'Адаптивный регулятор эффективнее классического ПИД на';
        animateNumber('sup-value', pct, '%', 1, '+');
        supValue.style.color = '#818cf8';
        supValue.style.textShadow = '0 0 20px rgba(129,140,248,0.7)';
        supDesc.textContent = 'Преимущество адаптивного регулятора по показателю ISE';
        supBlock.style.borderColor = 'rgba(129,140,248,0.4)';
      } else {
        // Классический лучше
        const pct = ((iseAI - isePID) / iseAI) * 100;
        supLabel.textContent = 'Классический ПИД точнее на';
        animateNumber('sup-value', pct, '%', 1, '+');
        supValue.style.color = '#38bdf8';
        supValue.style.textShadow = '0 0 20px rgba(56,189,248,0.7)';
        supDesc.textContent = 'Классический регулятор стабильнее по показателю ISE';
        supBlock.style.borderColor = 'rgba(56,189,248,0.4)';
      }
    }
  }
}

function updateEconomics(timeElapsed) {
  const costAI = (totGasAI + segGasAI) * 1800;
  const costPID = (totGasPID + segGasPID) * 1800;
  
  const totAiEl = document.getElementById('eco-tot-ai');
  const totPidEl = document.getElementById('eco-tot-pid');
  if (totAiEl) animateNumber('eco-tot-ai', costAI, ' UZS', 0);
  if (totPidEl) animateNumber('eco-tot-pid', costPID, ' UZS', 0);
}

// ====================== SEND CONTROLS ======================
async function sendControls(reset = false) {
  try {
    await fetch('/api/controls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        is_running: isRunning,
        target_sp: targetSP,
        gas_press: gasPress,
        oxygen_press: oxyPress,
        reset
      })
    });
  } catch(e) {
    console.warn('API не доступен:', e.message);
  }
}

// ====================== UI CONTROLS ======================
const btnToggle = document.getElementById('btn-toggle');
const btnReset  = document.getElementById('btn-reset');
const statusDot  = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');

btnToggle.addEventListener('click', () => {
  isRunning = !isRunning;
  btnToggle.textContent = isRunning ? '⏹ ОСТАНОВИТЬ' : '▶ ЗАПУСТИТЬ';
  btnToggle.classList.toggle('running', isRunning);
  statusDot.classList.toggle('running', isRunning);
  statusText.textContent = isRunning ? 'Работает...' : 'Остановлено';
  sendControls();
});

btnReset.addEventListener('click', () => {
  isRunning = false;
  btnToggle.textContent = '▶ ЗАПУСТИТЬ';
  btnToggle.classList.remove('running');
  statusDot.classList.remove('running');
  statusText.textContent = 'Остановлено';
  times = []; aiTemps = []; pidTemps = []; targets = [];
  kpData = []; kiData = []; kdData = [];
  totGasAI = 0; totOxyAI = 0; totGasPID = 0; totOxyPID = 0;
  segGasAI = 0; segOxyAI = 0; segGasPID = 0; segOxyPID = 0;
  lastLogMinute = 0;
  valveTravelAI = 0; valveTravelPID = 0;
  prevValveAI = 0; prevValvePID = 0;
  const tbody = document.getElementById('consumption-log');
  if (tbody) tbody.innerHTML = '';
  const ecoAiBody = document.getElementById('eco-log-ai');
  const ecoPidBody = document.getElementById('eco-log-pid');
  if (ecoAiBody) ecoAiBody.innerHTML = '';
  if (ecoPidBody) ecoPidBody.innerHTML = '';
  
  updateCharts();
  ['m-ai-temp','m-pid-temp','m-gas-flow','m-oxy-flow','kp-val','ki-val','kd-val','ise-ai','ise-pid','dev-ai','dev-pid',
   'tot-gas-ai', 'tot-gas-pid', 'tot-oxy-ai', 'tot-oxy-pid', 'eco-tot-ai', 'eco-tot-pid']
    .forEach(id => { const el = document.getElementById(id); if(el) el.textContent = '—'; });
  sendControls(true);
});

// Setpoint
const spDisplay = document.getElementById('sp-display');
document.getElementById('sp-minus').addEventListener('click', () => {
  targetSP = Math.max(100, targetSP - 10);
  spDisplay.textContent = targetSP;
  sendControls();
});
document.getElementById('sp-plus').addEventListener('click', () => {
  targetSP = Math.min(1650, targetSP + 10);
  spDisplay.textContent = targetSP;
  sendControls();
});

// init display
spDisplay.textContent = targetSP;

// Sliders
function initSlider(id, valId, setter) {
  const el = document.getElementById(id);
  const vl = document.getElementById(valId);
  el.addEventListener('input', () => {
    setter(parseFloat(el.value));
    vl.textContent = parseFloat(el.value).toFixed(2);
    sendControls();
  });
}
initSlider('gas-press', 'gas-val',  v => gasPress = v);
initSlider('oxy-press', 'oxy-val',  v => oxyPress = v);

// Navigation
window.showPage = function(pageId) {
  console.log('Navigating to:', pageId);
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const targetPage = document.getElementById('page-' + pageId);
  if (targetPage) {
    targetPage.classList.add('active');
    window.scrollTo(0, 0);
  } else {
    console.error('Page not found:', pageId);
  }
  
  const layout = document.getElementById('layout');
  if (layout) layout.classList.add('sidebar-hidden');

  if (window.lucide) window.lucide.createIcons();
};

// Initialize Menu Card Click Listeners
function initNavigation() {
  console.log('Initializing navigation listeners...');
  document.querySelectorAll('.menu-card').forEach(card => {
    card.addEventListener('click', () => {
      const target = card.getAttribute('data-target');
      if (target) window.showPage(target);
    });
  });
}


// ====================== INIT ======================
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  connectWS();
  if (window.lucide) window.lucide.createIcons();
});
