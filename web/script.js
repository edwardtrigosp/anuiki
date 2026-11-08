/* =========================================================
   CONFIGURACIÓN — cambia aquí la versión y los enlaces
   a tus instaladores reales (ej. carpeta /downloads o
   GitHub Releases).
   ========================================================= */
const APP_VERSION = "1.2.0";

const PLATFORMS = [
  {
    id: "windows",
    name: "Windows",
    detail: "Windows 10 / 11 · 64 bits",
    file: "https://github.com/edwardtrigosp/anuiki/releases/latest/download/Anuiki-Setup.exe",
    ext: ".exe",
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5 10.5 4.5v7H3zM11.5 4.3 21 3v8.5h-9.5zM3 12.5h7.5v7L3 18.5zM11.5 12.5H21V21l-9.5-1.3z"/></svg>`,
  },
];

/* ---------- Detección del sistema operativo ---------- */
function detectOS() {
  const ua = navigator.userAgent.toLowerCase();
  if (/android/.test(ua)) return "android";
  if (/iphone|ipad|ipod/.test(ua)) return null; // iOS sin instalador
  if (/win/.test(ua)) return "windows";
  if (/mac/.test(ua)) return "mac";
  if (/linux|x11/.test(ua)) return "linux";
  return null;
}

const currentOS = detectOS();
const downloadIcon = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12m0 0-5-5m5 5 5-5M5 20h14"/></svg>`;

/* ---------- Tarjetas de descarga ---------- */
const container = document.getElementById("downloads");
const ordered = [...PLATFORMS].sort((a, b) => (b.id === currentOS) - (a.id === currentOS));

container.innerHTML = ordered
  .map((p) => {
    const rec = p.id === currentOS;
    return `
      <article class="dl reveal ${rec ? "is-recommended" : ""}">
        ${rec ? '<span class="dl__badge">Tu sistema</span>' : ""}
        <div class="dl__icon">${p.icon}</div>
        <h3>${p.name}</h3>
        <small>${p.detail}</small>
        <small>Versión ${APP_VERSION} · ${p.ext}</small>
        <a class="btn btn--purple btn--sm" href="${p.file}" download>
          ${downloadIcon} Descargar
        </a>
      </article>`;
  })
  .join("");

/* ---------- Botón principal del hero ---------- */
const primary = PLATFORMS.find((p) => p.id === currentOS);
document.getElementById("version-pill").textContent = `v${APP_VERSION}`;
if (primary) {
  const btn = document.getElementById("primary-download");
  btn.href = primary.file;
  btn.setAttribute("download", "");
  document.getElementById("primary-icon").innerHTML = primary.icon;
  document.getElementById("primary-label").textContent = `Descargar para ${primary.name}`;
  document.getElementById("detected-os").textContent =
    `Gratis · Windows 10 / 11 · 64 bits`;
}

/* ---------- Nav al hacer scroll ---------- */
const nav = document.querySelector(".nav");
const onScroll = () => nav.classList.toggle("is-scrolled", window.scrollY > 40);
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

/* ---------- Animaciones de entrada ---------- */
const observer = new IntersectionObserver(
  (entries) =>
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add("is-visible");
        observer.unobserve(e.target);
      }
    }),
  { threshold: 0.15 }
);
document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

document.getElementById("year").textContent = new Date().getFullYear();
