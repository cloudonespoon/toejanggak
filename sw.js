/* 퇴장각 오프라인 캐시
   공연 직후 수만 명이 한꺼번에 휴대폰을 쓰면 통신이 느려지거나 끊긴다.
   한 번 연 뒤에는 저장된 파일로 바로 뜨고(캐시 우선), 온라인이면 뒤에서 새 파일로 갱신한다.
   배포할 때 CACHE 이름(버전)을 바꾸면 이전 캐시는 지워진다. */
const CACHE = "toejanggak-v4";
const ASSETS = ["./", "index.html", "style.css?v=4", "app.js?v=4", "data.js?v=4",
  "manifest.webmanifest", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return; // 글꼴 등 외부 파일은 그대로
  e.respondWith(caches.open(CACHE).then(async (c) => {
    const hit = await c.match(req, { ignoreSearch: req.mode === "navigate" });
    const update = fetch(req).then((res) => {
      if (res && res.ok) c.put(req, res.clone());
      return res;
    }).catch(() => null);
    if (hit) { e.waitUntil(update); return hit; }
    const res = await update;
    return res || (req.mode === "navigate" ? c.match("index.html") : Response.error());
  }));
});
