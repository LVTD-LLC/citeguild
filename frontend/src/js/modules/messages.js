export function initMessages(root = document) {
  root.querySelectorAll("[data-message-item]").forEach((item, index) => {
    window.setTimeout(() => {
      item.classList.remove("opacity-0", "translate-x-full");
      startTimer(item);
    }, index * 100);
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-message-dismiss]");
    if (!button) {
      return;
    }

    const item = button.closest("[data-message-item]");
    if (item) {
      hideMessage(item);
    }
  });
}

export function showMessage(message, type = "error") {
  const container = document.querySelector("[data-messages-container]") || createMessagesContainer();
  const item = buildMessageElement(message, type);

  container.appendChild(item);
  window.setTimeout(() => {
    item.classList.remove("opacity-0", "translate-x-full");
    startTimer(item);
  }, 100);
}

function createMessagesContainer() {
  const container = document.createElement("div");
  container.dataset.messagesContainer = "";
  container.className = "fixed top-4 right-4 z-50 space-y-4";
  document.body.appendChild(container);
  return container;
}

function buildMessageElement(message, type) {
  const isError = type === "error";
  const item = document.createElement("div");
  item.dataset.messageItem = "";
  item.className = `max-w-sm translate-x-full rounded-lg border p-4 opacity-0 shadow-sm transition-all duration-300 ease-in-out ${isError ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50"}`;

  item.innerHTML = `
    <div class="flex items-start">
      <div class="mr-3 flex-shrink-0">
        <svg class="h-5 w-5" viewBox="0 0 24 24">
          <circle class="text-gray-200" stroke-width="2" stroke="currentColor" fill="transparent" r="10" cx="12" cy="12"></circle>
          <circle class="${isError ? "text-red-600" : "text-green-600"}" stroke-width="2" stroke="currentColor" fill="transparent" r="10" cx="12" cy="12" data-timer-circle></circle>
        </svg>
      </div>
      <div class="flex-grow">
        <p class="text-sm ${isError ? "text-red-800" : "text-green-800"}"></p>
      </div>
      <div class="ml-3 flex-shrink-0">
        <button data-message-dismiss type="button" class="inline-flex h-5 w-5 items-center justify-center rounded-md ${isError ? "text-red-600 hover:text-red-800 focus:ring-red-500" : "text-green-600 hover:text-green-800 focus:ring-green-500"} focus:outline-none focus:ring-2 focus:ring-offset-2">
          <span class="sr-only">Dismiss</span>
          <svg class="h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>
    </div>
  `;
  item.querySelector("p").textContent = message;
  return item;
}

function startTimer(item) {
  const timerCircle = item.querySelector("[data-timer-circle]");
  if (!timerCircle) {
    return;
  }

  const radius = 10;
  const circumference = 2 * Math.PI * radius;
  timerCircle.style.strokeDasharray = `${circumference} ${circumference}`;
  timerCircle.style.strokeDashoffset = circumference;

  let progress = 0;
  const interval = window.setInterval(() => {
    if (progress >= 100) {
      window.clearInterval(interval);
      hideMessage(item);
      return;
    }

    progress += 1;
    timerCircle.style.strokeDashoffset = circumference - (progress / 100) * circumference;
  }, 50);
}

function hideMessage(item) {
  item.classList.add("opacity-0", "translate-x-full");
  window.setTimeout(() => item.remove(), 300);
}
