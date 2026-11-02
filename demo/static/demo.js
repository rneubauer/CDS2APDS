/* Civic District demo page. Vanilla JS, no build step, no network beyond this server.
   Every panel is a live call to the link service; the map is drawn from /demo/upstream.json
   (the fictional CDS and APDS records) plus GET /links. */
"use strict";

(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const EARTH_R = 6371008.8;
  const STEP_ZONES = {
    t1: "3f2a9c1e-5b7d-4e8a-9c01-00000000b001", // garage entry apron
    t2: "3f2a9c1e-5b7d-4e8a-9c01-00000000b002", // full metered block
    t3: "3f2a9c1e-5b7d-4e8a-9c01-00000000b003", // Zone A resident permit
  };
  const VALID_RESULTS = new Set(["valid"]);
  const NEUTRAL_RESULTS = new Set(["no_programme"]);
  const RESULT_TEXT = {
    valid: "Valid: the permit is honoured here",
    not_found: "Not found: no matching permit in this programme",
    expired: "Expired",
    not_yet_valid: "Not yet valid",
    programme_inactive: "Programme inactive",
    no_programme: "No permit programme on this curb",
  };
  const NEARBY_KM = 0.6; // places further than this from the zones are drawn as off-map markers

  const state = { data: null, links: [], selected: null, offStreet: null, names: new Map(), mapSize: 0 };

  /* ---------- small DOM helpers (textContent only, never innerHTML with data) ---------- */
  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    setAttrs(node, attrs);
    append(node, children);
    return node;
  }
  function s(tag, attrs, ...children) {
    const node = document.createElementNS(SVG_NS, tag);
    setAttrs(node, attrs);
    append(node, children);
    return node;
  }
  function setAttrs(node, attrs) {
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.setAttribute("class", v);
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, String(v));
    }
  }
  function append(node, children) {
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
  }
  function $(id) { return document.getElementById(id); }
  function replace(target, ...children) {
    const node = typeof target === "string" ? $(target) : target;
    node.replaceChildren();
    append(node, children);
  }
  function badge(text, cls) { return h("span", { class: "badge " + cls }, text); }
  function shortId(id) { return "…" + String(id).slice(-4); }
  function nameOf(id) { return state.names.get(id) || shortId(id); }
  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toISOString().replace("T", " ").replace(/\.\d+Z$|Z$/, " UTC");
  }

  /* ---------- API ---------- */
  async function api(method, path, body, rawId) {
    const init = { method, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const started = performance.now();
    let status = 0;
    let json = null;
    let failure = null;
    try {
      const resp = await fetch(path, init);
      status = resp.status;
      json = await resp.json();
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
    }
    const ms = Math.round(performance.now() - started);
    if (rawId) showRaw(rawId, method, path, body, status, json, ms, failure);
    if (failure) throw new Error(`${method} ${path} failed: ${failure}`);
    if (!json || json.success !== true) {
      const msg = json && json.error ? `${json.error.code}: ${json.error.message}` : `HTTP ${status}`;
      throw new Error(`${method} ${path}: ${msg}`);
    }
    return json.data;
  }

  function showRaw(rawId, method, path, body, status, json, ms, failure) {
    const lines = [`${method} ${path}`];
    if (body !== undefined) lines.push(JSON.stringify(body, null, 2));
    lines.push("", failure ? `request failed: ${failure}` : `HTTP ${status} · ${ms} ms`);
    if (json !== null) lines.push(JSON.stringify(json, null, 2));
    $(rawId).querySelector("pre").textContent = lines.join("\n");
  }

  function showError(targetId, err) {
    replace(targetId, h("p", { class: "error" }, err.message));
  }

  /* ---------- data lookups ---------- */
  const zones = () => state.data.cds.zones;
  const areas = () => state.data.cds.areas;
  const policies = () => state.data.cds.policies;
  const elements = () => state.data.apds.elements;
  const specs = () => state.data.apds.right_specs;
  const zoneById = (id) => zones().find((z) => z.curb_zone_id === id);
  const elementById = (id) => elements().find((e) => e.id === id);
  const enName = (names) => {
    if (!Array.isArray(names) || !names.length) return null;
    const en = names.find((n) => n.language === "en");
    return (en || names[0]).string;
  };
  function shortZoneName(zone) {
    const parts = String(zone.name || zone.curb_zone_id).split(" - ");
    const tail = parts[parts.length - 1];
    return tail.charAt(0).toUpperCase() + tail.slice(1);
  }
  function buildNames() {
    zones().forEach((z) => state.names.set(z.curb_zone_id, z.name));
    areas().forEach((a) => state.names.set(a.curb_area_id, a.name));
    policies().forEach((p) => state.names.set(p.curb_policy_id, p.name));
    elements().forEach((e) => state.names.set(e.id, enName(e.name) || e.id));
    specs().forEach((r) => state.names.set(r.id, enName(r.description) || r.id));
  }

  /* ---------- geometry ---------- */
  function ringOf(geometry) {
    if (!geometry) return [];
    if (geometry.type === "Polygon") return geometry.coordinates[0].slice(0, -1);
    if (geometry.type === "LineString") return geometry.coordinates;
    return [];
  }
  function centroidOf(geometry) {
    const pts = ringOf(geometry);
    const n = pts.length || 1;
    return [pts.reduce((a, p) => a + p[0], 0) / n, pts.reduce((a, p) => a + p[1], 0) / n];
  }
  function pointOf(element) {
    const loc = element.indicativePointLocation;
    return Array.isArray(loc) && loc[0] && loc[0].coordinates ? loc[0].coordinates : null;
  }
  function haversineKm(a, b) {
    const rad = Math.PI / 180;
    const dLat = (b[1] - a[1]) * rad;
    const dLng = (b[0] - a[0]) * rad;
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLng / 2) ** 2;
    return (2 * EARTH_R * Math.asin(Math.sqrt(x))) / 1000;
  }

  function zonesCentre() {
    const pts = zones().flatMap((z) => ringOf(z.geometry));
    return [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length];
  }

  function spanX(pts) { const xs = pts.map((p) => p[0]); return Math.max(...xs) - Math.min(...xs); }
  function spanY(pts) { const ys = pts.map((p) => p[1]); return Math.max(...ys) - Math.min(...ys); }

  function makeProjection(width, height) {
    const zonePts = zones().flatMap((z) => ringOf(z.geometry));
    const centre = zonesCentre();
    const near = elements().map(pointOf).filter((p) => p && haversineKm(centre, p) <= NEARBY_KM);
    const pts = zonePts.concat(near);
    const kx = Math.cos((centre[1] * Math.PI) / 180); // equirectangular, scaled at this latitude
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const [lng, lat] of pts) {
      minX = Math.min(minX, lng * kx); maxX = Math.max(maxX, lng * kx);
      minY = Math.min(minY, lat); maxY = Math.max(maxY, lat);
    }
    const pad = 70;
    const padRight = Math.min(170, width * 0.3); // point labels sit to the right of their markers
    const scale = Math.min((width - pad - padRight) / (maxX - minX || 1e-6), (height - 2 * pad) / (maxY - minY || 1e-6));
    const offX = pad + (width - pad - padRight - (maxX - minX) * scale) / 2;
    const offY = (height - (maxY - minY) * scale) / 2;
    const project = ([lng, lat]) => [offX + (lng * kx - minX) * scale, offY + (maxY - lat) * scale];
    const metresPerPx = (((Math.PI / 180) * EARTH_R) / scale);
    return { project, metresPerPx, width, height };
  }

  /* ---------- map ---------- */
  function renderMap() {
    const svg = $("map");
    const width = Math.max(300, Math.round(svg.parentElement.clientWidth));
    const height = Math.round(Math.min(680, Math.max(320, width * 0.95)));
    state.mapSize = width;
    svg.classList.toggle("narrow", width < 480); // phones: drop secondary labels
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    svg.replaceChildren();
    const proj = makeProjection(width, height);
    const P = proj.project;
    const inView = ([x, y]) => x >= 0 && x <= width && y >= 0 && y <= height;
    const pathOf = (pts) => "M" + pts.map((p) => P(p).map((v) => v.toFixed(1)).join(",")).join("L") + "Z";

    const gArea = s("g");
    const gRadius = s("g", { id: "radius-layer" });
    const gLinks = s("g");
    const gZones = s("g");
    const gPoints = s("g");
    const gLabels = s("g");
    svg.append(gArea, gRadius, gLinks, gZones, gPoints, gLabels);

    // Curb areas (dashed outline) with a label anchored at their visible top-left corner.
    const areaAnchor = new Map();
    for (const area of areas()) {
      const ring = ringOf(area.geometry);
      if (!ring.length) continue;
      gArea.append(s("path", { class: "area", d: pathOf(ring) }));
      const xs = ring.map((p) => P(p)[0]);
      const ys = ring.map((p) => P(p)[1]);
      const ax = Math.max(Math.min(...xs), 0) + 12;
      const ay = Math.max(Math.min(...ys), 0) + 22;
      areaAnchor.set(area.curb_area_id, [ax, ay + 10]);
      gLabels.append(s("text", { class: "lbl-strong", x: ax, y: ay }, `${area.name} (curb area)`));
    }

    // Links.
    const zoneCentre = new Map(zones().map((z) => [z.curb_zone_id, P(centroidOf(z.geometry))]));
    const elementPt = new Map(elements().map((e) => [e.id, pointOf(e) ? P(pointOf(e)) : null]));
    const endFor = (cds) => {
      if (cds.type === "CurbZone") return zoneCentre.get(cds.id);
      if (cds.type === "CurbArea") return areaAnchor.get(cds.id);
      return null;
    };
    for (const link of state.links) {
      if (link.kind === "permit") {
        drawPermitLink(gLinks, gLabels, link, zoneCentre, elementPt);
        continue;
      }
      const a = endFor(link.cds);
      const b = elementPt.get(link.apds.id);
      if (!a || !b) continue;
      drawLink(gLinks, gLabels, link, a, b, link.kind === "access" ? "T1" : "T2");
    }

    // Curb zones. Labels of side-by-side horizontal zones are staggered so they don't collide.
    const horizontal = zones()
      .filter((z) => { const r = ringOf(z.geometry).map(P); return r.length && spanX(r) >= spanY(r); })
      .sort((a, b) => P(centroidOf(a.geometry))[0] - P(centroidOf(b.geometry))[0])
      .map((z) => z.curb_zone_id);
    for (const zone of zones()) {
      const ring = ringOf(zone.geometry);
      if (!ring.length) continue;
      const d = pathOf(ring);
      const group = s("g", {
        class: "zone-group" + (zone.curb_zone_id === state.selected ? " selected" : ""),
        tabindex: 0, role: "button", "data-zone": zone.curb_zone_id,
        "aria-label": `Select curb zone ${zone.name}`,
        onclick: () => selectZone(zone.curb_zone_id),
        onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selectZone(zone.curb_zone_id); } },
      },
      s("title", {}, zone.name),
      s("path", { class: "zone-hit", d }),
      s("path", { class: "zone-sel", d }),
      s("path", { class: "zone", d }));
      gZones.append(group);
      const xs = ring.map((p) => P(p)[0]);
      const ys = ring.map((p) => P(p)[1]);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      const label = shortZoneName(zone);
      if (maxX - minX >= maxY - minY) {
        const row = horizontal.indexOf(zone.curb_zone_id) % 2;
        gLabels.append(s("text", { class: "lbl zone-label", x: (minX + maxX) / 2, y: maxY + 20 + row * 18, "text-anchor": "middle" }, label));
      } else {
        gLabels.append(s("text", { class: "lbl zone-label", x: minX - 10, y: (minY + maxY) / 2, "text-anchor": "end" }, label));
      }
    }

    // APDS places and entrances.
    for (const el of elements()) {
      const pt = pointOf(el);
      if (!pt) continue;
      const [x, y] = P(pt);
      const label = enName(el.name) || el.id;
      if (el.type === "vehicularAccess") {
        gPoints.append(s("rect", { class: "access", x: x - 6, y: y - 6, width: 12, height: 12 }, s("title", {}, label)));
        gLabels.append(s("text", { class: "lbl zone-label", x: x + 32, y: y + 5 }, "Entrance (" + (el.accessType || "access") + ")"));
        continue;
      }
      if (inView([x, y])) {
        gPoints.append(s("circle", { class: "place", "data-place": el.id, cx: x, cy: y, r: 9 }, s("title", {}, label)));
        gLabels.append(s("text", { class: "lbl-strong", x: x + 14, y: y - 8 }, label));
      } else {
        drawOffMap(gPoints, gLabels, el, `${label}, ${haversineKm(zonesCentre(), pt).toFixed(1)} km`, [x, y], proj);
      }
    }

    drawScaleBar(svg, proj);
    highlightOffStreet();
  }

  function drawLink(gLinks, gLabels, link, a, b, tag) {
    const cls = `link link-${link.kind}`;
    const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const colour = tag === "T1" ? "#B5650A" : "#1E75BB";
    if (dist < 28) {
      // Endpoints nearly coincide at this scale (an entrance is metres from its curb): ring them.
      const cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2, r = 22 + dist / 2;
      gLinks.append(s("circle", { class: cls, cx, cy, r, "data-link": link.kind }));
      gLabels.append(s("text", { class: "lbl-link", x: cx - r - 6, y: cy - r + 4, "text-anchor": "end", fill: colour }, `${tag} ${link.kind}`));
      return;
    }
    gLinks.append(s("line", { class: cls, x1: a[0], y1: a[1], x2: b[0], y2: b[1], "data-link": link.kind }));
    const lx = a[0] + (b[0] - a[0]) * 0.7, ly = a[1] + (b[1] - a[1]) * 0.7;
    gLabels.append(s("text", { class: "lbl-link", x: lx - 8, y: ly + 18, "text-anchor": "end", fill: colour }, `${tag} ${link.kind}`));
  }

  // A permit link joins a curb policy to a RightSpecification. On the map: from every zone that
  // uses the policy to every facility listed in the specification's hierarchyElements.
  function drawPermitLink(gLinks, gLabels, link, zoneCentre, elementPt) {
    const spec = specs().find((r) => r.id === link.apds.id);
    const targets = ((spec && spec.hierarchyElements) || []).map((ref) => elementPt.get(ref.id)).filter(Boolean);
    const users = zones().filter((z) => (z.curb_policy_ids || []).includes(link.cds.id));
    for (const zone of users) {
      const a = zoneCentre.get(zone.curb_zone_id);
      for (const b of targets) {
        const cx = (a[0] + b[0]) / 2, cy = Math.min(a[1], b[1]) - 60; // bow upwards, away from the street
        gLinks.append(s("path", {
          class: "link link-permit", "data-link": "permit",
          d: `M${a[0]},${a[1]} Q${cx},${cy} ${b[0]},${b[1]}`,
        }));
        const mx = (a[0] + 2 * cx + b[0]) / 4, my = (a[1] + 2 * cy + b[1]) / 4;
        gLabels.append(s("text", { class: "lbl-link", x: mx, y: my - 10, "text-anchor": "middle", fill: "#67308F" }, "T3 permit"));
      }
    }
  }

  function drawOffMap(gPoints, gLabels, el, label, [x, y], proj) {
    const cx = proj.width / 2, cy = proj.height / 2;
    const t = Math.min(
      x > cx ? (proj.width - 24 - cx) / (x - cx) : x < cx ? (24 - cx) / (x - cx) : Infinity,
      y > cy ? (proj.height - 24 - cy) / (y - cy) : y < cy ? (24 - cy) / (y - cy) : Infinity,
    );
    const ex = cx + (x - cx) * t, ey = cy + (y - cy) * t;
    const ang = (Math.atan2(y - cy, x - cx) * 180) / Math.PI;
    gPoints.append(s("path", {
      class: "offmap place", "data-place": el.id, d: "M10,0 L-6,-8 L-6,8 Z",
      transform: `translate(${ex.toFixed(1)},${ey.toFixed(1)}) rotate(${ang.toFixed(1)})`,
    }, s("title", {}, `${label} (off the map)`)));
    const right = ex > cx;
    gLabels.append(s("text", { class: "lbl", x: ex + (right ? -4 : 4), y: ey + 30, "text-anchor": right ? "end" : "start" }, label));
  }

  function drawScaleBar(svg, proj) {
    const metres = 50;
    const px = metres / proj.metresPerPx;
    const x = 16, y = proj.height - 16;
    svg.append(s("g", { class: "scale" },
      s("line", { x1: x, y1: y, x2: x + px, y2: y }),
      s("line", { x1: x, y1: y - 5, x2: x, y2: y + 1 }),
      s("line", { x1: x + px, y1: y - 5, x2: x + px, y2: y + 1 }),
      s("text", { class: "lbl", x: x + px + 8, y: y + 4 }, `${metres} m`)));
  }

  function highlightOffStreet() {
    const svg = $("map");
    const layer = $("radius-layer");
    if (layer) layer.replaceChildren();
    const result = state.offStreet;
    const hits = new Set(result && result.curb_zone_id === state.selected ? result.places.map((p) => p.id) : []);
    svg.querySelectorAll(".place[data-place]").forEach((node) => {
      node.classList.toggle("hit", hits.has(node.dataset.place));
      node.classList.toggle("miss", result !== null && !hits.has(node.dataset.place));
    });
    if (!result || result.curb_zone_id !== state.selected || !layer) return;
    const proj = makeProjection(Number(svg.getAttribute("width")), Number(svg.getAttribute("height")));
    const [x, y] = proj.project([result.origin.lng, result.origin.lat]);
    layer.append(s("circle", { class: "radius", cx: x, cy: y, r: result.radius_m / proj.metresPerPx }));
  }

  /* ---------- zone selection ---------- */
  function selectZone(zoneId, step) {
    if (!zoneById(zoneId)) return;
    state.selected = zoneId;
    document.querySelectorAll("#map .zone-group").forEach((g) => g.classList.toggle("selected", g.dataset.zone === zoneId));
    document.querySelectorAll(".step").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.step === step)));
    $("p-zone").value = zoneId;
    renderZoneInfo();
    runT1();
    runT2();
    runT3();
  }

  function renderZoneInfo() {
    const zone = zoneById(state.selected);
    const bits = [];
    if (typeof zone.num_spaces === "number" && typeof zone.available_spaces === "number") {
      bits.push(`CDS reports ${zone.available_spaces} of ${zone.num_spaces} spaces free`);
    }
    const pols = (zone.curb_policy_ids || []).map(nameOf);
    if (pols.length) bits.push("Policy: " + pols.join(", "));
    replace("zone-info",
      h("strong", {}, zone.name),
      h("span", { class: "muted small" }, bits.join(" · ")),
      h("div", { class: "mono small muted" }, "curb_zone_id " + zone.curb_zone_id));
  }

  /* ---------- T1 ---------- */
  async function runT1() {
    const zoneId = state.selected;
    try {
      const links = await api("GET", `/links?cds_id=${encodeURIComponent(zoneId)}`, undefined, "t1-raw");
      if (zoneId !== state.selected) return;
      const zone = zoneById(zoneId);
      const items = links.map(linkItem);
      if (!links.some((l) => l.kind === "access")) {
        items.unshift(h("p", {}, "No access link: no facility entrance sits on this curb zone."));
      }
      const viaArea = state.links.filter((l) => l.cds.type === "CurbArea" && (zone.curb_area_ids || []).includes(l.cds.id));
      if (viaArea.length) {
        items.push(h("p", { class: "note" }, `Via its curb area: ${viaArea.map((l) => `${nameOf(l.cds.id)} → ${nameOf(l.apds.id)} (${l.kind})`).join("; ")}.`));
      }
      replace("t1-body", items);
    } catch (err) { showError("t1-body", err); }
  }

  function linkItem(link) {
    const kindTag = { access: "T1", supply: "T2", permit: "T3" }[link.kind];
    const statusText = {
      confirmed: "confirmed: declared on both sides",
      cds_only: "one-sided: declared in CDS only",
      apds_only: "one-sided: declared in APDS only",
    }[link.status] || link.status;
    return h("div", { class: "link-item" },
      h("div", {}, badge(`${kindTag} ${link.kind}`, "b-" + kindTag.toLowerCase()), " ",
        badge(statusText, link.status === "confirmed" ? "b-ok" : "b-neutral")),
      h("div", { class: "ends" },
        h("span", {}, h("strong", {}, link.cds.type), " ", nameOf(link.cds.id)),
        h("span", { class: "arrow", "aria-hidden": "true" }, "↔"),
        h("span", {}, h("strong", {}, link.apds.type), " ", nameOf(link.apds.id))),
      link.kind === "access" ? h("p", { class: "note" },
        "CDS side: ", h("code", {}, "external_references[].reference_url"), " · APDS side: ",
        h("code", {}, "operatorDefinedReference.className = CdsCurbZone")) : null);
  }

  /* ---------- T2 ---------- */
  async function runT2() {
    const zoneId = state.selected;
    const radius = $("radius").value;
    try {
      const data = await api("GET", `/zones/${encodeURIComponent(zoneId)}/off-street?radius_m=${radius}`, undefined, "t2-raw");
      if (zoneId !== state.selected) return;
      state.offStreet = data;
      highlightOffStreet();
      const rows = data.places.map((p) => h("tr", { class: p.linked ? "linked" : "" },
        h("td", {}, h("strong", {}, p.name || p.id), p.access_points.length
          ? h("div", { class: "small muted" }, "Entrance: " + p.access_points.map((a) => a.name || a.id).join(", ")) : null),
        h("td", {}, p.linked ? badge("linked", "b-t2") : badge("radius only", "b-neutral")),
        h("td", { class: "num" }, p.distance_m === null ? "—" : `${p.distance_m} m`),
        h("td", { class: "num" }, p.spaces_available === null ? "unknown" : `${p.spaces_available} / ${p.spaces_total}`),
        h("td", {}, p.open_to_public === null ? "—" : p.open_to_public ? "yes" : "no"),
        h("td", { class: "small" }, fmtTime(p.occupancy_time))));
      replace("t2-body",
        h("p", { class: "small muted" },
          `${data.places.length} place(s) within ${data.radius_m} m of the zone centroid `,
          h("span", { class: "mono" }, `${data.origin.lat}, ${data.origin.lng}`),
          ". Linked places come first, then by distance."),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {},
            h("th", { scope: "col" }, "Place"), h("th", { scope: "col" }, "Link"),
            h("th", { scope: "col", class: "num" }, "Distance"), h("th", { scope: "col", class: "num" }, "Free / total"),
            h("th", { scope: "col" }, "Public"), h("th", { scope: "col" }, "Occupancy at"))),
          h("tbody", {}, rows))),
        h("p", { class: "note" }, "“unknown” means APDS publishes no occupancy: the service never assumes a facility has space."));
    } catch (err) { showError("t2-body", err); }
  }

  /* ---------- T3 ---------- */
  async function runT3() {
    const zoneId = $("p-zone").value;
    const credential = $("p-cred").value;
    const type = $("p-type").value;
    const at = $("p-at").value.trim();
    if (!credential.trim()) { replace("t3-body", h("p", { class: "error" }, "Enter a credential.")); return; }
    const body = { curb_zone_id: zoneId, credential };
    if (type) body.credential_type = type;
    if (at) body.at = at;
    try {
      const data = await api("POST", "/permits/verify", body, "t3-raw");
      const cls = VALID_RESULTS.has(data.result) ? "b-ok" : NEUTRAL_RESULTS.has(data.result) ? "b-neutral" : "b-bad";
      const progs = data.programmes.length
        ? data.programmes.map((p) => `${nameOf(p.curb_policy_id)} → ${nameOf(p.right_specification_id)}`).join("; ")
        : "none (no permit rule with an APDS reference)";
      const right = data.assigned_right
        ? `${shortId(data.assigned_right.id)} v${data.assigned_right.version}, expires ${fmtTime(data.assigned_right.expiry)}`
        : "—";
      replace("t3-body",
        h("div", { class: "decision" }, badge(RESULT_TEXT[data.result] || data.result, cls)),
        h("dl", { class: "kv" },
          h("dt", {}, "Zone"), h("dd", {}, nameOf(data.curb_zone_id)),
          h("dt", {}, "Credential"), h("dd", {}, h("span", { class: "mono" }, data.credential_masked), " (masked by the service; never logged)"),
          h("dt", {}, "Checked at"), h("dd", {}, fmtTime(data.at)),
          h("dt", {}, "Programme"), h("dd", {}, progs),
          h("dt", {}, "Assigned right"), h("dd", {}, right)));
    } catch (err) { showError("t3-body", err); }
  }

  /* ---------- registry panel ---------- */
  async function refreshRegistry() {
    try {
      const [health, links, issues] = await Promise.all([
        api("GET", "/health", undefined, "health-raw"),
        api("GET", "/links", undefined, "links-raw"),
        api("GET", "/issues", undefined, "issues-raw"),
      ]);
      state.links = links;
      replace("health-line", `Service ${health.status} · ${health.links} links · last sync ${fmtTime(health.last_sync)}`);
      const rows = links.map((l) => h("tr", {},
        h("td", {}, badge(l.kind, "b-" + { access: "t1", supply: "t2", permit: "t3" }[l.kind])),
        h("td", {}, badge(l.status, l.status === "confirmed" ? "b-ok" : "b-neutral")),
        h("td", {}, h("strong", {}, l.cds.type), " ", nameOf(l.cds.id)),
        h("td", {}, h("strong", {}, l.apds.type), " ", nameOf(l.apds.id))));
      replace("links-body", h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Kind"), h("th", { scope: "col" }, "Status"),
          h("th", { scope: "col" }, "CDS (on-street)"), h("th", { scope: "col" }, "APDS (off-street)"))),
        h("tbody", {}, rows))));
      replace("issues-body", issues.length
        ? h("ul", {}, issues.map((i) => h("li", {}, badge(i.code, "b-bad"), " ", i.detail)))
        : h("p", { class: "note" }, "No issues: every declared link resolves on both sides."));
      return true;
    } catch (err) {
      showError("links-body", err);
      return false;
    }
  }

  async function resync() {
    const btn = $("resync");
    btn.disabled = true;
    try {
      await api("POST", "/sync", undefined, "health-raw");
      await refreshRegistry();
      renderMap();
    } catch (err) {
      showError("links-body", err);
    } finally {
      btn.disabled = false;
    }
  }

  /* ---------- wiring ---------- */
  function wire() {
    document.querySelectorAll(".step").forEach((btn) => btn.addEventListener("click", () => {
      const step = btn.dataset.step;
      selectZone(STEP_ZONES[step], step);
      const card = $(step);
      card.classList.remove("flash");
      void card.offsetWidth; // restart the highlight animation
      card.classList.add("flash");
      if (window.matchMedia("(max-width: 980px)").matches) card.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
    $("radius").addEventListener("change", runT2);
    $("permit-form").addEventListener("submit", (ev) => { ev.preventDefault(); runT3(); });
    $("p-zone").addEventListener("change", runT3);
    document.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
      $("p-cred").value = chip.dataset.cred;
      $("p-type").value = chip.dataset.type;
      $("p-at").value = chip.dataset.at;
      runT3();
    }));
    $("resync").addEventListener("click", resync);
    let timer = 0;
    window.addEventListener("resize", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (Math.abs($("map").parentElement.clientWidth - state.mapSize) > 8) renderMap();
      }, 150);
    });
  }

  async function init() {
    wire();
    try {
      const resp = await fetch("upstream.json");
      if (!resp.ok) throw new Error(`upstream.json: HTTP ${resp.status}`);
      state.data = await resp.json();
      buildNames();
      replace("p-zone", zones().map((z) => h("option", { value: z.curb_zone_id }, z.name)));
      await refreshRegistry();
      state.selected = STEP_ZONES.t1;
      renderMap();
      selectZone(STEP_ZONES.t1, "t1");
    } catch (err) {
      const fatal = $("fatal");
      fatal.hidden = false;
      fatal.textContent = "Demo failed to load: " + err.message;
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
