const form = document.querySelector("#jobForm");
const calibrationCard = document.querySelector("#calibrationCard");
const progressCard = document.querySelector("#progressCard");
const canvas = document.querySelector("#calibrationCanvas");
const ctx = canvas.getContext("2d");
const undoPoint = document.querySelector("#undoPoint");
const resetPoints = document.querySelector("#resetPoints");
const sendCalibration = document.querySelector("#sendCalibration");
const pointStatus = document.querySelector("#pointStatus");
const progressBar = document.querySelector("#progressBar");
const progressText = document.querySelector("#progressText");
const summary = document.querySelector("#summary");
const downloadBtn = document.querySelector("#downloadBtn");

let jobId = null;
let points = [];
let image = new Image();

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = new FormData();
  const video = document.querySelector("#video").files[0];
  const url = document.querySelector("#youtube_url").value.trim();

  if (video) data.append("video", video);
  if (url) data.append("youtube_url", url);
  if (!video && !url) return;

  progressCard.classList.remove("hidden");
  progressText.textContent = "Creating job…";

  const res = await fetch("/api/jobs", { method: "POST", body: data });
  const body = await res.json();
  if (!res.ok) {
    progressText.textContent = body.detail || "Could not create job.";
    return;
  }

  jobId = body.job_id;
  points = Array.isArray(body.auto_corners) ? body.auto_corners : [];
  image.src = `/api/jobs/${jobId}/calibration-frame`;
  image.onload = () => {
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    draw();
    calibrationCard.classList.remove("hidden");
    progressCard.classList.add("hidden");
    calibrationCard.scrollIntoView({ behavior: "smooth" });
  };
});

function draw() {
  if (!image.complete) return;
  ctx.drawImage(image, 0, 0);
  points.forEach((p, i) => {
    ctx.beginPath();
    ctx.arc(p[0], p[1], 11, 0, Math.PI * 2);
    ctx.fillStyle = i < 4 ? "#f1c84b" : i === 4 ? "#67df91" : "#ff7f7f";
    ctx.fill();
    ctx.fillStyle = "#111";
    ctx.font = "bold 16px sans-serif";
    ctx.fillText(String(i + 1), p[0] - 5, p[1] + 5);
  });
  pointStatus.textContent = `${points.length} of 6 points selected`;
  sendCalibration.disabled = points.length !== 6;
}

canvas?.addEventListener("pointerdown", (e) => {
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * canvas.width / rect.width;
  const y = (e.clientY - rect.top) * canvas.height / rect.height;

  // After automatic detection, the next taps become colour samples.
  if (points.length < 6) points.push([x, y]);
  draw();
});

undoPoint?.addEventListener("click", () => {
  points.pop();
  draw();
});

resetPoints?.addEventListener("click", () => {
  points = [];
  draw();
});

sendCalibration?.addEventListener("click", async () => {
  const res = await fetch(`/api/jobs/${jobId}/calibrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ points }),
  });
  const body = await res.json();
  if (!res.ok) {
    pointStatus.textContent = body.detail || "Calibration failed.";
    return;
  }

  calibrationCard.classList.add("hidden");
  progressCard.classList.remove("hidden");
  progressCard.scrollIntoView({ behavior: "smooth" });
  poll();
});

async function poll() {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (res.status === 401) {
    window.location.href = "/login";
    return;
  }
  const body = await res.json();

  progressBar.style.width = `${body.progress || 0}%`;
  progressText.textContent = body.message || body.stage;

  if (body.stage === "complete") {
    const s = body.summary;
    summary.innerHTML = `
      <div><strong>${s.positions_detected}</strong><br>Positions</div>
      <div><strong>${s.moves_inferred}</strong><br>Moves</div>
      <div><strong>${s.uncertain_positions}</strong><br>Needs review</div>`;
    downloadBtn.href = `/api/jobs/${jobId}/download`;
    downloadBtn.classList.remove("hidden");
    return;
  }

  if (body.stage === "error") return;
  setTimeout(poll, 1500);
}
