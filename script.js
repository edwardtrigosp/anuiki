/* =========================================================
   CONFIGURACIÓN — cambia aquí la versión y los enlaces
   a tus instaladores reales (ej. carpeta /downloads o
   GitHub Releases).
   ========================================================= */
const APP_VERSION = "1.3.1";

const PLATFORMS = [
  {
    id: "windows",
    name: "Windows",
    detail: "Windows 10 / 11 · 64 bits",
    // El instalador lleva la versión en el nombre (Anuiki-Setup-1.3.1.exe) y se enlaza a esa versión exacta.
    file: `https://github.com/edwardtrigosp/anuiki/releases/download/v${APP_VERSION}/Anuiki-Setup-${APP_VERSION}.exe`,
    ext: ".exe",
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5 10.5 4.5v7H3zM11.5 4.3 21 3v8.5h-9.5zM3 12.5h7.5v7L3 18.5zM11.5 12.5H21V21l-9.5-1.3z"/></svg>`,
  },
];

/* =========================================================
   NOVEDADES — añade la versión nueva ARRIBA del todo.
   Cada entrada: versión, fecha y 2-4 viñetas cortas.
   Se muestran las 3 primeras; el resto queda plegado.
   ========================================================= */
const NOVEDADES = [
  {
    version: "1.3.1",
    fecha: "9 de noviembre de 2026",
    cambios: [
      "Barra rediseñada: más pequeña y redondeada, con la onda de voz, el tiempo de grabación y un acceso directo a Configuración. Su opacidad se puede ajustar.",
      "Avisa cuando el micrófono está apagado o desconectado, también antes de grabar, y te dice si no se escuchó nada porque estuvo apagado.",
      "Nueva guía de uso con los atajos (Ctrl+Espacio, Espacio y Esc). Se abre sola la primera vez y siempre desde el engranaje de la barra.",
      "Tipografía libre Manrope e iconos más nítidos en toda la aplicación.",
    ],
  },
  {
    version: "1.3.0",
    fecha: "9 de noviembre de 2026",
    cambios: [
      "Al dictar en una terminal (Windows Terminal, PowerShell, cmd…), el texto se envía solo con Enter. Ideal para Claude Code u OpenCode. Se puede desactivar en Configuración.",
      "Ahora puedes detener la grabación pulsando solo Espacio, sin repetir el atajo de inicio. Se puede desactivar en Configuración.",
      "Nuevo atajo por defecto: Ctrl+Espacio para empezar a dictar, Espacio para terminar y Esc para cancelar. La barra muestra estos atajos mientras grabas.",
      "Aviso de micrófono sin señal: si está silenciado o desconectado, la barra te pide activarlo y, si la grabación queda vacía, te lo indica.",
    ],
  },
  {
    version: "1.2.0",
    fecha: "8 de noviembre de 2026",
    cambios: [
      "Transcripción mientras hablas: Anuiki trabaja por trozos durante la grabación, así que al terminar casi no hay espera.",
      "Sonidos nuevos, suaves y discretos, al empezar a grabar y al terminar de transcribir.",
      "La barra se ajusta al texto, ya no se corta y nunca queda fuera de la pantalla.",
    ],
  },
  {
    version: "1.0.0 – 1.1.0",
    fecha: "7 de noviembre de 2026",
    cambios: [
      "Primeras versiones: dictado en español con reconocimiento 100 % local, atajo global, icono en la bandeja y historial de dictados.",
    ],
  },
];

const changelog = document.getElementById("changelog");
const entradaHTML = (n, i) => `
  <article class="release reveal">
    <header class="release__head">
      <span class="release__ver">v${n.version}</span>
      ${i === 0 ? '<span class="release__tag">Última</span>' : ""}
      <time class="release__date">${n.fecha}</time>
    </header>
    <ul>${n.cambios.map((c) => `<li>${c}</li>`).join("")}</ul>
  </article>`;
const VISIBLES = 3;
changelog.innerHTML =
  NOVEDADES.slice(0, VISIBLES).map(entradaHTML).join("") +
  (NOVEDADES.length > VISIBLES
    ? `<details class="changelog__more"><summary>Ver versiones anteriores</summary>${NOVEDADES.slice(VISIBLES)
        .map((n, i) => entradaHTML(n, i + VISIBLES))
        .join("")}</details>`
    : "");

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
