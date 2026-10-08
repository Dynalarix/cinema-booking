// Клиентская часть справочной службы. Общается с бэкендом через REST API (/api/...).

let token = localStorage.getItem("token");
let currentUser = null;
let cinemas = [];
let films = [];

// ---------- Работа с API ----------

async function api(path, options = {}) {
  const headers = {};
  if (token) headers["Authorization"] = "Bearer " + token;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const response = await fetch("/api" + path, { method: options.method || "GET", headers, body: options.body });

  // Токен просрочен или неверный — возвращаемся на экран входа
  if (response.status === 401 && token) {
    logout();
    throw new Error("Сессия истекла, войдите снова");
  }
  if (response.status === 204) return null;

  const data = await response.json();
  if (!response.ok) throw new Error(errorText(data));
  return data;
}

// Превращает ответ FastAPI с ошибкой в понятный текст
function errorText(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((e) => `${e.loc[e.loc.length - 1]}: ${e.msg}`).join("; ");
  }
  return "Ошибка запроса";
}

function showMessage(text, ok = false) {
  const el = document.getElementById("message");
  el.textContent = text;
  el.className = ok ? "message ok" : "message";
  el.hidden = false;
  clearTimeout(showMessage.timer);
  showMessage.timer = setTimeout(() => (el.hidden = true), 4000);
}

// ---------- Вход и выход ----------

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "";
  try {
    // Логин отправляется как форма (так требует OAuth2 в FastAPI)
    const data = await api("/auth/login", { method: "POST", body: new URLSearchParams(new FormData(event.target)) });
    token = data.access_token;
    localStorage.setItem("token", token);
    event.target.reset();
    await start();
  } catch (e) {
    errorEl.textContent = e.message;
  }
});

document.getElementById("logout").addEventListener("click", logout);

function logout() {
  token = null;
  currentUser = null;
  localStorage.removeItem("token");
  document.getElementById("app-view").hidden = true;
  document.getElementById("login-view").hidden = false;
}

async function start() {
  currentUser = await api("/auth/me");
  const isAdmin = currentUser.role === "admin";
  document.getElementById("user-info").textContent =
    `${currentUser.username} (${isAdmin ? "администратор" : "сотрудник"})`;
  // Формы добавления/изменения видит только администратор
  document.querySelectorAll(".admin-only").forEach((el) => (el.hidden = !isAdmin));
  document.getElementById("login-view").hidden = true;
  document.getElementById("app-view").hidden = false;
  await loadAll();
}

// ---------- Вкладки ----------

document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b === button));
    document.querySelectorAll(".tab").forEach((tab) => (tab.hidden = tab.id !== "tab-" + button.dataset.tab));
  });
});

// ---------- Таблицы ----------

const formatDate = (value) => value.split("-").reverse().join(".");
const formatTime = (value) => value.slice(0, 5);

// Колонки таблиц: [поле, заголовок, функция форматирования (необязательно)]
const COLUMNS = {
  cinemas: [["name", "Название"], ["address", "Адрес"], ["category", "Категория"],
            ["seats_count", "Кол. мест"], ["halls_count", "Кол. залов"], ["status", "Состояние"]],
  films: [["title", "Название"], ["director", "Режиссёр"], ["operator", "Оператор"],
          ["actors", "Актёры"], ["genre", "Жанр"], ["studio", "Киностудия"]],
  screenings: [["date", "Дата", formatDate], ["time", "Сеанс", formatTime], ["cinema_name", "Кинотеатр"],
               ["hall", "Зал"], ["film_title", "Фильм"], ["price", "Цена, ₽"], ["free_seats", "Свободных мест"]],
};

// Строит таблицу. actions(row) возвращает список кнопок для строки.
function renderTable(table, columns, rows, actions) {
  table.innerHTML = "";
  if (rows.length === 0) {
    table.innerHTML = '<tr><td class="empty">Нет данных</td></tr>';
    return;
  }
  const head = table.insertRow();
  for (const [, title] of columns) head.appendChild(document.createElement("th")).textContent = title;
  if (actions) head.appendChild(document.createElement("th"));

  for (const row of rows) {
    const tr = table.insertRow();
    for (const [field, , format] of columns) {
      // textContent, а не innerHTML — чтобы данные не могли внедрить HTML-код
      tr.insertCell().textContent = format ? format(row[field]) : row[field];
    }
    if (actions) {
      const cell = tr.insertCell();
      for (const [label, className, handler] of actions(row)) {
        const button = cell.appendChild(document.createElement("button"));
        button.textContent = label;
        button.className = className;
        button.addEventListener("click", handler);
      }
    }
  }
}

function rowActions(entity, row) {
  const actions = [];
  if (entity === "screenings") actions.push(["Продать билеты", "", () => sellTickets(row)]);
  if (currentUser.role === "admin") {
    actions.push(["Изменить", "secondary", () => startEdit(entity, row)]);
    actions.push(["Удалить", "danger", () => remove(entity, row)]);
  }
  return actions;
}

async function loadAll() {
  try {
    const [c, f, s] = await Promise.all([api("/cinemas"), api("/films"), api("/screenings")]);
    cinemas = c;
    films = f;
    const data = { cinemas: c, films: f, screenings: s };
    for (const entity of Object.keys(COLUMNS)) {
      renderTable(document.getElementById(entity + "-table"), COLUMNS[entity], data[entity],
                  (row) => rowActions(entity, row));
    }
    fillSelects();
  } catch (e) {
    showMessage(e.message);
  }
}

// Заполняет выпадающие списки кинотеатров и фильмов, сохраняя выбранное значение
function fillSelects() {
  const fill = (select, items, label) => {
    const selected = select.value;
    select.innerHTML = "";
    for (const item of items) select.add(new Option(label(item), item.id));
    if (selected) select.value = selected;
  };
  document.querySelectorAll(".cinema-select").forEach((s) => fill(s, cinemas, (c) => c.name));
  document.querySelectorAll(".film-select").forEach((s) => fill(s, films, (f) => f.title));
}

// ---------- Добавление, изменение, удаление ----------

// Собирает данные формы в объект; числовые поля превращает в числа
function formToObject(form) {
  const data = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    data[el.name] = el.type === "number" || "number" in el.dataset ? Number(el.value) : el.value;
  }
  return data;
}

function startEdit(entity, row) {
  const form = document.getElementById(entity + "-form");
  for (const el of form.elements) {
    if (!el.name) continue;
    el.value = el.name === "time" ? formatTime(row[el.name]) : row[el.name];
  }
  form.dataset.editId = row.id;
  form.querySelector("[type=submit]").textContent = "Сохранить";
  form.querySelector(".cancel").hidden = false;
  form.scrollIntoView({ behavior: "smooth" });
}

function resetForm(form) {
  form.reset();
  delete form.dataset.editId;
  form.querySelector("[type=submit]").textContent = "Добавить";
  form.querySelector(".cancel").hidden = true;
}

for (const entity of Object.keys(COLUMNS)) {
  const form = document.getElementById(entity + "-form");
  form.querySelector(".cancel").addEventListener("click", () => resetForm(form));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = form.dataset.editId;
    try {
      // Есть editId — изменяем запись (PUT), нет — добавляем новую (POST)
      await api(id ? `/${entity}/${id}` : `/${entity}`, { method: id ? "PUT" : "POST", json: formToObject(form) });
      resetForm(form);
      showMessage(id ? "Изменения сохранены" : "Запись добавлена", true);
      await loadAll();
    } catch (e) {
      showMessage(e.message);
    }
  });
}

async function remove(entity, row) {
  const warning = entity === "screenings" ? "" : "\nВсе связанные сеансы тоже будут удалены.";
  if (!confirm("Удалить запись?" + warning)) return;
  try {
    await api(`/${entity}/${row.id}`, { method: "DELETE" });
    showMessage("Запись удалена", true);
    await loadAll();
  } catch (e) {
    showMessage(e.message);
  }
}

async function sellTickets(row) {
  const answer = prompt(`Сколько билетов продать? Свободно мест: ${row.free_seats}`, "1");
  if (answer === null) return;
  try {
    await api(`/screenings/${row.id}/sell`, { method: "POST", json: { count: Number(answer) } });
    showMessage("Билеты проданы", true);
    await loadAll();
  } catch (e) {
    showMessage(e.message);
  }
}

// ---------- Запросы справочной службы ----------

// Подключает обработчик к форме запроса: load(данные формы) должен вернуть функцию отрисовки результата
function setupQuery(id, load) {
  const form = document.getElementById(id);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = form.querySelector(".result");
    try {
      const params = Object.fromEntries(new FormData(form));
      await load(params, result, form);
    } catch (e) {
      result.innerHTML = "";
      result.appendChild(document.createElement("p")).textContent = e.message;
    }
  });
}

function resultTable(container, columns, rows) {
  container.innerHTML = '<div class="table-wrap"><table></table></div>';
  renderTable(container.querySelector("table"), columns, rows);
}

setupQuery("q-repertoire", async ({ cinema_id }, result) => {
  const rows = await api(`/queries/repertoire/${cinema_id}`);
  resultTable(result, COLUMNS.screenings.filter(([f]) => f !== "cinema_name"), rows);
});

async function cinemasByGenre(params, result, form) {
  const rows = await api("/queries/cinemas-by-genre?genre=" + encodeURIComponent(form.dataset.genre));
  resultTable(result, [["name", "Кинотеатр"], ["address", "Адрес"]], rows);
}
setupQuery("q-action", cinemasByGenre);
setupQuery("q-comedy", cinemasByGenre);

async function sessionQuery(params, result, field, title) {
  const rows = await api("/queries/session?" + new URLSearchParams(params));
  resultTable(result, [["hall", "Зал"], ["film_title", "Фильм"], [field, title]], rows);
}
setupQuery("q-free-seats", (params, result) => sessionQuery(params, result, "free_seats", "Свободных мест"));
setupQuery("q-price", (params, result) => sessionQuery(params, result, "price", "Цена, ₽"));

setupQuery("q-director", async ({ director }, result) => {
  const rows = await api("/queries/films-by-director?director=" + encodeURIComponent(director));
  resultTable(result, COLUMNS.films.filter(([f]) => f !== "actors"), rows);
});

// ---------- Ассистент ----------

const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatLog = document.getElementById("chat-log");

// Добавляет сообщение в журнал чата. Если переданы колонки и данные — рисует таблицу.
function chatPost(role, reply) {
  const message = document.createElement("div");
  message.className = "chat-message chat-" + role;
  const text = document.createElement("p");
  text.textContent = reply.text;
  message.appendChild(text);
  if (reply.columns && reply.columns.length && reply.rows && reply.rows.length) {
    const wrap = message.appendChild(document.createElement("div"));
    wrap.className = "table-wrap";
    const table = wrap.appendChild(document.createElement("table"));
    const head = table.insertRow();
    for (const column of reply.columns) {
      head.appendChild(document.createElement("th")).textContent = column.title;
    }
    for (const row of reply.rows) {
      const tr = table.insertRow();
      for (const column of reply.columns) {
        tr.insertCell().textContent = row[column.field] ?? "";
      }
    }
  }
  chatLog.appendChild(message);
  chatLog.scrollTop = chatLog.scrollHeight;
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatPost("user", { text: message });
  chatInput.value = "";
  chatInput.disabled = true;
  try {
    const reply = await api("/assistant/ask", { method: "POST", json: { message } });
    chatPost("bot", reply);
  } catch (e) {
    chatPost("bot", { text: "Ошибка: " + e.message });
  } finally {
    chatInput.disabled = false;
    chatInput.focus();
  }
});

// ---------- Запуск ----------

// Если токен сохранился с прошлого раза — сразу открываем приложение
if (token) start().catch(logout);
