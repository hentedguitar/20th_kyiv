var g_latlng;
(function () {
  "use strict";

  // Кордони Києва з kyiv_outline.js: контури, кожна точка — [широта, довгота].
  // KYIV_RINGS[0] — зовнішня межа міста, решта — «дірки» всередині нього.
  var KYIV_RINGS = window.KYIV_OUTLINE_RINGS;
  if (!KYIV_RINGS || !KYIV_RINGS.length) {
    var errEl = document.getElementById("map-status");
    if (errEl) {
      errEl.hidden = false;
      errEl.textContent = "Не вдалося завантажити кордони Києва (kyiv_outline.js).";
      errEl.classList.add("map-status--error");
    }
    return;
  }
  var KYIV_OUTLINE = KYIV_RINGS[0];
  var KYIV_BOUNDS = L.latLngBounds(KYIV_OUTLINE);

  var statusEl = document.getElementById("map-status");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Мапа ---------- */
  var map = L.map("map", {
    zoomSnap: 0.25,
    maxBoundsViscosity: 1.0   // не дає «витягнути» мапу за межі
  });

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; учасники <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>"
  }).addTo(map);

  function lockToBounds(bounds) {
    map.setMaxBounds(bounds);
    map.setMinZoom(map.getBoundsZoom(bounds));   // не дає віддалити мапу далі міста
    map.fitBounds(bounds);
  }
  lockToBounds(KYIV_BOUNDS);

  /* ---------- Повідомлення на мапі ---------- */
  var statusTimer = null;
  function showStatus(text, isError, autoHideMs) {
    if (!statusEl) return;
    clearTimeout(statusTimer);
    statusEl.hidden = false;
    statusEl.textContent = text;
    statusEl.classList.toggle("map-status--error", !!isError);
    if (autoHideMs) statusTimer = setTimeout(hideStatus, autoHideMs);
  }
  function hideStatus() {
    if (statusEl) statusEl.hidden = true;
  }

  /* ---------- Контур Києва та перевірка «точка всередині» ---------- */
  function getCss(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // Показуємо контур, щоб було видно, де можна ставити точки; клікам він не заважає
  var outlineLayer = L.polygon(KYIV_RINGS, {
    interactive: false,
    color: getCss("--district-stroke"),
    weight: 2,
    dashArray: "8 6",
    fillColor: getCss("--district-fill"),
    fillOpacity: 0.08
  }).addTo(map);

  document.addEventListener("themechange", function () {
    outlineLayer.setStyle({
      color: getCss("--district-stroke"),
      fillColor: getCss("--district-fill")
    });
  });

  // Алгоритм променя: рахуємо перетини променя з ребрами контура
  function ringContains(ring, x, y) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var yi = ring[i][0], xi = ring[i][1];
      var yj = ring[j][0], xj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  // Всередині зовнішнього контура і поза «дірками»
  function isInsideKyiv(latlng) {
    if (!ringContains(KYIV_RINGS[0], latlng.lng, latlng.lat)) return false;
    for (var k = 1; k < KYIV_RINGS.length; k++) {
      if (ringContains(KYIV_RINGS[k], latlng.lng, latlng.lat)) return false;
    }
    return true;
  }

  showStatus("Натисніть на мапу, щоб поставити точку", false, 4000);

  /* ---------- Перемикач теми ---------- */
  var toggle = document.getElementById("theme-toggle");

  function syncToggle() {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    toggle.setAttribute("aria-checked", dark ? "true" : "false");
  }
  syncToggle();

  toggle.addEventListener("click", function () {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    syncToggle();
    document.dispatchEvent(new Event("themechange"));
  });

  /* ---------- Повзунок епох: плавний рух + зміна тексту ---------- */
  var slider = document.getElementById("year-slider");
  var yearOut = document.getElementById("year-output");
  const periods = {
    1: 'Українська революція',
    2: 'Міжвоєнний період',
    3: 'Друга світова війна',
    4: 'Повоєнна відбудова',
    5: 'Відлига',
    6: 'Застій',
    7: 'Перебудова'
  };
  var FIRST = 1, LAST = 7;
  var currentPeriod = 1;
  var rafId = null;

  // Оновлює текст, лише коли найближча епоха змінилась
  function renderPeriod(n) {
    if (n === currentPeriod) return;
    currentPeriod = n;
    yearOut.textContent = periods[n];
    slider.setAttribute("aria-valuetext", periods[n]);

    if (!reduceMotion && yearOut.animate) {
      yearOut.animate(
        [{ opacity: 0, transform: "translateY(0.15em)" }, { opacity: 1, transform: "none" }],
        { duration: 240, easing: "ease-out" }
      );
    }
    document.dispatchEvent(new CustomEvent("yearchange", { detail: { period: n, name: periods[n] } }));
  }

  function cancelAnim() {
    if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
  }

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  // Плавно «доїжджає» повзунком до цілого значення
  function animateTo(target) {
    cancelAnim();
    var from = parseFloat(slider.value);
    if (from === target) { renderPeriod(target); return; }
    if (reduceMotion) { slider.value = target; renderPeriod(target); return; }

    var duration = 200 + Math.abs(target - from) * 250;
    var start = null;

    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min((ts - start) / duration, 1);
      var value = from + (target - from) * easeInOutCubic(t);
      slider.value = value;
      renderPeriod(Math.round(value));
      if (t < 1) {
        rafId = requestAnimationFrame(step);
      } else {
        rafId = null;
        slider.value = target;
        renderPeriod(target);
      }
    }
    rafId = requestAnimationFrame(step);
  }

  // Під час перетягування текст змінюється разом із повзунком
  slider.addEventListener("input", function () {
    cancelAnim();
    renderPeriod(Math.round(parseFloat(slider.value)));
  });
  // Після відпускання — плавно до найближчої епохи
  slider.addEventListener("change", function () {
    animateTo(Math.round(parseFloat(slider.value)));
  });
  slider.addEventListener("pointerdown", cancelAnim);

  // Клавіатура: стрілки переходять на сусідню епоху
  slider.addEventListener("keydown", function (e) {
    var cur = Math.round(parseFloat(slider.value));
    var target = null;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") target = Math.min(cur + 1, LAST);
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") target = Math.max(cur - 1, FIRST);
    else if (e.key === "Home") target = FIRST;
    else if (e.key === "End") target = LAST;
    if (target === null) return;
    e.preventDefault();
    animateTo(target);
  });

  /* ---------- Точка користувача: що вона означає, вирішує Python-бекенд ---------- */
  var USER_POINT_URL = "/api/user-point";

  var panel = document.getElementById("point-panel");
  var panelTitle = document.getElementById("point-panel-title");
  var panelClose = document.getElementById("panel-close");
  var stateEl = document.getElementById("point-state");
  var dataList = document.getElementById("point-data");
  var DEFAULT_TITLE = "Точка на мапі";

  var userMarker = null;   // точка, яку поставив користувач
  var nearestLayer = L.layerGroup().addTo(map); // п’ять найближчих історичних точок
  var requestId = 0;       // щоб запізніла відповідь на попередню точку не перезаписала панель

  var userIcon = L.divIcon({
    className: "point-marker is-selected",
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });

  function errText(err) {
    return err instanceof TypeError
      ? "Немає зв'язку з бекендом. Запустіть python backend/server.py."
      : err.message;
  }

  function askBackend(latlng, period) {
    return fetch(USER_POINT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_point: [latlng.lat, latlng.lng], period: period })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || "Помилка сервера (" + response.status + ")");
        return data.result;
      });
    });
  }

  /* --- Панель (лише перегляд) --- */
  function showState(text, isError) {
    stateEl.hidden = false;
    stateEl.textContent = text;
    stateEl.classList.toggle("is-error", !!isError);
  }

  function setRows(rows) {
    dataList.textContent = "";
    rows.forEach(function (row) {
      var dt = document.createElement("dt");
      var dd = document.createElement("dd");
      dt.textContent = row[0];
      dd.textContent = row[1];
      if (row[2]) dd.className = "is-text";
      dataList.appendChild(dt);
      dataList.appendChild(dd);
    });
    dataList.hidden = rows.length === 0;
  }

  // Показуємо найближчі події у панелі та їхні маркери на мапі.
  function renderResult(data) {
    nearestLayer.clearLayers();

    if (!Array.isArray(data) || data.length === 0) {
      showState("Поруч не знайдено історичних подій.");
      dataList.hidden = true;
      return;
    }

    stateEl.hidden = true;
    dataList.textContent = "";
    panelTitle.textContent = "Найближчі історичні локації";

    data.forEach(function (point, index) {
      if (point.coordinates && point.coordinates.length === 2) {
        var marker = L.marker(point.coordinates).addTo(nearestLayer);
        marker.bindPopup(String(point.title || "Історична подія"));
      }

      var heading = document.createElement("dt");
      var title = document.createElement("strong");
      title.textContent = "#" + (index + 1) + ": " + (point.title || "Подія");
      heading.appendChild(title);
      if (point.date) heading.appendChild(document.createTextNode(" (" + point.date + ")"));
      dataList.appendChild(heading);

      var details = document.createElement("dd");
      details.className = "is-text";
      var description = document.createElement("p");
      description.textContent = point.description || "Опис цієї події поки відсутній.";
      heading.appendChild(description);

      if (point.period_name) {
        var period = document.createElement("p");
        period.textContent = "Епоха: " + point.period_name;
        heading.appendChild(period);
      }
      if (point.source_url) {
        var link = document.createElement("a");
        link.href = point.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Джерело";
        heading.appendChild(link);
      }
      dataList.appendChild(details);
    });

    dataList.hidden = false;
  }


  function openPanel() {
    panel.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
    panelClose.focus({ preventScroll: true });
  }

  // Закриття панелі = розфокус: точка зникає з мапи
  function closePanel() {
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
    requestId++;
    if (userMarker) {
      map.removeLayer(userMarker);
      userMarker = null;
    }
    nearestLayer.clearLayers();
  }

  function placeUserPoint(latlng, period) {
    nearestLayer.clearLayers();
    if (userMarker) map.removeLayer(userMarker);   // попередня точка зникає
    userMarker = L.marker(latlng, { icon: userIcon, interactive: false, keyboard: false }).addTo(map);
    var id = ++requestId;

    panelTitle.textContent = DEFAULT_TITLE;
    setRows([]);
    showState("Запитуємо бекенд…");
    openPanel();

    // На широких екранах панель закриває праву частину мапи — зсуваємо мапу
    if (window.innerWidth > 640) {
      var x = map.latLngToContainerPoint(latlng).x;
      var overlap = x - (map.getSize().x - panel.offsetWidth - 48);
      if (overlap > 0) map.panBy([overlap, 0]);
    }

    askBackend(latlng, period)
      .then(function (result) { if (id === requestId) renderResult(result); })
      .catch(function (err) { if (id === requestId) showState(errText(err), true); });
  }

  /* --- Події --- */
  // Клік по мапі: нова точка (лише всередині Києва), попередня зникає
  map.addEventListener("click", function (e) {
    if (!isInsideKyiv(e.latlng)) {
      showStatus("Ця точка поза межами Києва. Оберіть місце в межах міста.", true, 3500);
      return;
    }
    hideStatus();
    placeUserPoint(e.latlng, slider.value);
    g_latlng = e.latlng;
  });
  slider.addEventListener("change", function () {
    placeUserPoint(g_latlng, Math.round(parseFloat(slider.value)).toString());
  });

  panelClose.addEventListener("click", closePanel);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && panel.classList.contains("is-open")) closePanel();
  });
})();
