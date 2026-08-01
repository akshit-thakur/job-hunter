"use strict";

const API_BASE = "http://127.0.0.1:9000";
const REQUEST_TIMEOUT_MS = 5000;

const form = document.getElementById("application-form");
const submitButton = document.getElementById("submit");
const companyInput = document.getElementById("company");
const connection = document.getElementById("connection");
const stats = document.getElementById("stats");
const message = document.getElementById("message");

function clean(value) {
  return value.trim();
}

function setConnection(isOnline) {
  connection.className = "connection " + (isOnline ? "online" : "offline");
  connection.title = isOnline ? "Tracker online" : "Tracker offline";
  connection.setAttribute("aria-label", connection.title);
}

function showMessage(text, kind) {
  message.textContent = text;
  message.className = "message" + (kind ? " " + kind : "");
}

function apiError(body, fallback) {
  if (!body || !body.detail) {
    return fallback;
  }
  if (typeof body.detail === "string") {
    return body.detail;
  }
  if (Array.isArray(body.detail)) {
    return body.detail.map(function (item) {
      return item.msg || "Invalid value";
    }).join(" ");
  }
  return fallback;
}

class ApiResponseError extends Error {}

async function fetchJson(path, options) {
  const controller = new AbortController();
  const timeout = window.setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(API_BASE + path, {
      ...options,
      signal: controller.signal,
      headers: {
        "Accept": "application/json",
        ...(options && options.headers ? options.headers : {})
      }
    });
    const body = await response.json().catch(function () { return null; });
    if (!response.ok) {
      throw new ApiResponseError(apiError(body, "Tracker returned HTTP " + response.status + "."));
    }
    return body;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function refreshStats() {
  try {
    const body = await fetchJson("/stats");
    setConnection(true);
    stats.textContent = "This week: " + body.submitted_this_week + " | Active: " + body.active;
  } catch (_error) {
    setConnection(false);
    stats.textContent = "Tracker offline";
  }
}

form.addEventListener("submit", async function (event) {
  event.preventDefault();
  if (!form.reportValidity()) {
    return;
  }

  const payload = {
    company: clean(form.elements.company.value),
    role: clean(form.elements.role.value),
    url: clean(form.elements.url.value) || null,
    notes: clean(form.elements.notes.value) || null,
    status: "applied"
  };

  submitButton.disabled = true;
  submitButton.textContent = "Saving...";
  showMessage("");

  try {
    await fetchJson("/applications", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    form.reset();
    companyInput.focus();
    setConnection(true);
    showMessage("Application saved.", "success");
    await refreshStats();
  } catch (error) {
    const isOffline = !(error instanceof ApiResponseError);
    setConnection(!isOffline);
    const text = isOffline
      ? "Tracker is offline. Start Docker and try again."
      : error.message;
    showMessage(text, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Log application";
  }
});

refreshStats();
