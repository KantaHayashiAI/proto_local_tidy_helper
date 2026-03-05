const svg = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#2b8a6e"/>
      <stop offset="100%" stop-color="#f2b84b"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="56" height="56" rx="18" fill="#0f1720"/>
  <path d="M18 36c0-9.94 8.06-18 18-18h10v8H36c-5.52 0-10 4.48-10 10v10h-8V36z" fill="url(#g)"/>
  <path d="M42 18h4c2.21 0 4 1.79 4 4v24c0 2.21-1.79 4-4 4H30v-8h12V18z" fill="#dce7e2"/>
  <circle cx="25" cy="46" r="4" fill="#f2b84b"/>
</svg>
`;

export function getTrayIconDataUrl() {
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}
