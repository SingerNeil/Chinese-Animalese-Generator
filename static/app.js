const elements = {
  text: document.querySelector("#scriptText"),
  characterCount: document.querySelector("#characterCount"),
  voice: document.querySelector("#voice"),
  speed: document.querySelector("#speed"),
  speedValue: document.querySelector("#speedValue"),
  pitch: document.querySelector("#pitch"),
  pitchValue: document.querySelector("#pitchValue"),
  variation: document.querySelector("#variation"),
  variationValue: document.querySelector("#variationValue"),
  pauseScale: document.querySelector("#pauseScale"),
  pauseValue: document.querySelector("#pauseValue"),
  dehiss: document.querySelector("#dehiss"),
  backend: document.querySelector("#backend"),
  seed: document.querySelector("#seed"),
  generateButton: document.querySelector("#generateButton"),
  variationButton: document.querySelector("#variationButton"),
  visualizer: document.querySelector("#visualizer"),
  canvas: document.querySelector("#waveform"),
  audio: document.querySelector("#audioPlayer"),
  duration: document.querySelector("#durationValue"),
  size: document.querySelector("#sizeValue"),
  resultState: document.querySelector("#resultState"),
  download: document.querySelector("#downloadLink"),
  message: document.querySelector("#message"),
};

let waveformBuffer = null;

function updateLabels() {
  elements.characterCount.textContent = `${elements.text.value.length} / 600`;
  elements.speedValue.textContent = `${Number(elements.speed.value).toFixed(2)}×`;
  const pitch = Number(elements.pitch.value);
  elements.pitchValue.textContent = `${pitch >= 0 ? "+" : ""}${pitch}`;
  elements.variationValue.textContent = `${Math.round(Number(elements.variation.value) * 100)}%`;
  elements.pauseValue.textContent = `${Math.round(Number(elements.pauseScale.value) * 100)}%`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function setBusy(isBusy) {
  elements.generateButton.disabled = isBusy;
  elements.variationButton.disabled = isBusy;
  elements.visualizer.dataset.state = isBusy ? "loading" : elements.visualizer.dataset.state;
  elements.resultState.dataset.state = isBusy ? "loading" : elements.resultState.dataset.state;
  elements.resultState.textContent = isBusy ? "正在生成" : elements.resultState.textContent;
  elements.generateButton.querySelector("span:last-child").textContent = isBusy ? "处理中…" : "生成语音";
}

function setMessage(text) {
  const copy = elements.message.querySelector("p");
  if (copy) copy.textContent = text;
}

function showError(message) {
  elements.resultState.dataset.state = "error";
  elements.resultState.textContent = "生成失败";
  elements.message.classList.add("is-error");
  setMessage(message);
}

function drawWaveform(buffer = waveformBuffer) {
  const canvas = elements.canvas;
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  if (!buffer) return;

  const samples = buffer.getChannelData(0);
  const bars = Math.max(48, Math.floor(rect.width / 5));
  const stride = Math.max(1, Math.floor(samples.length / bars));
  const center = rect.height / 2;
  const maximumHeight = rect.height * 0.39;
  const gradient = context.createLinearGradient(0, 0, rect.width, 0);
  gradient.addColorStop(0, "#2c6956");
  gradient.addColorStop(0.62, "#96d3bd");
  gradient.addColorStop(1, "#b093cc");
  context.fillStyle = gradient;

  for (let index = 0; index < bars; index += 1) {
    const start = index * stride;
    const end = Math.min(samples.length, start + stride);
    let peak = 0;
    for (let sampleIndex = start; sampleIndex < end; sampleIndex += 1) {
      peak = Math.max(peak, Math.abs(samples[sampleIndex]));
    }
    const height = Math.max(3, peak * maximumHeight);
    const x = (index / bars) * rect.width;
    context.roundRect(x, center - height, 2.4, height * 2, 2);
    context.fill();
  }
}

async function loadWaveform(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("无法读取生成的音频");
  const audioData = await response.arrayBuffer();
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  const context = new AudioContext();
  try {
    waveformBuffer = await context.decodeAudioData(audioData.slice(0));
    drawWaveform();
  } finally {
    await context.close();
  }
}

function buildPayload() {
  const seed = elements.seed.value.trim();
  return {
    text: elements.text.value,
    voice: elements.voice.value,
    speed: Number(elements.speed.value),
    pitch: Number(elements.pitch.value),
    variation: Number(elements.variation.value),
    pauseScale: Number(elements.pauseScale.value),
    dehiss: elements.dehiss.value,
    backend: elements.backend.value,
    seed: seed === "" ? null : Number(seed),
  };
}

async function generateAudio() {
  const payload = buildPayload();
  if (!payload.text.trim()) {
    showError("请先输入要生成的文字。");
    elements.text.focus();
    return;
  }

  setBusy(true);
  elements.message.classList.remove("is-error");
  setMessage("正在拼接音素并处理音高、语速和停顿…");

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "生成失败");

    elements.audio.pause();
    elements.audio.src = `${result.audioUrl}?t=${Date.now()}`;
    elements.audio.load();
    elements.duration.textContent = `${result.duration.toFixed(2)} 秒`;
    elements.size.textContent = formatBytes(result.sizeBytes);
    elements.download.href = result.downloadUrl;
    elements.download.classList.remove("is-disabled");
    elements.download.removeAttribute("aria-disabled");
    elements.visualizer.dataset.state = "ready";
    elements.resultState.dataset.state = "ready";
    elements.resultState.textContent = "可以试听";
    setMessage("已在本机生成。满意后可直接下载 WAV。");
    await loadWaveform(result.audioUrl);
  } catch (error) {
    showError(error instanceof Error ? error.message : "生成失败");
  } finally {
    setBusy(false);
  }
}

function generateVariation() {
  const values = new Uint32Array(1);
  crypto.getRandomValues(values);
  elements.seed.value = String(values[0] & 0x7fffffff);
  generateAudio();
}

elements.text.addEventListener("input", updateLabels);
for (const input of [elements.speed, elements.pitch, elements.variation, elements.pauseScale]) {
  input.addEventListener("input", updateLabels);
}
elements.generateButton.addEventListener("click", generateAudio);
elements.variationButton.addEventListener("click", generateVariation);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    generateAudio();
  }
});
window.addEventListener("resize", () => drawWaveform());

updateLabels();
drawWaveform(null);

